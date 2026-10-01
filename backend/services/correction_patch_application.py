from __future__ import annotations

from collections.abc import Callable
from typing import Any

from harnesses.structured_patch.patch_signatures import (
    attribute_remove_blocked_by_deferred_relationship_reason,
    normalized_operation_signature_payload,
)
from core.schemas import StructuredModel
from backend.services.correction_patch_application_events import emit_operation_candidate
from backend.services.correction_patch_application_queue import CorrectionPatchOperationQueue
from backend.services.correction_patch_application_state import (
    CorrectionPatchApplicationResult,
    CorrectionPatchApplicationState,
)
from harnesses.structured_patch.correction_policy import CorrectionOperationGuard
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)


class CorrectionPatchBatchApplier:
    def __init__(
        self,
        *,
        job_id: str,
        model: StructuredModel,
        specification: str,
        allowed_ops: set[str],
        emit: Callable[[str, dict[str, Any]], None],
        operation_guard: CorrectionOperationGuard | None = None,
        name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
    ) -> None:
        self.job_id = job_id
        self.specification = specification
        self.allowed_ops = allowed_ops
        self.emit = emit
        self.operation_guard = operation_guard
        self.name_policy = name_policy
        self.state = CorrectionPatchApplicationState(
            job_id=job_id,
            model=model,
            emit=emit,
            name_policy=name_policy,
        )
        self.queue = CorrectionPatchOperationQueue(name_policy=name_policy)

    def operation_guard_reason(self, operation: dict[str, Any]) -> str | None:
        if self.operation_guard is None:
            return None
        return self.operation_guard(operation, self.model, self.specification)

    @property
    def model(self) -> StructuredModel:
        return self.state.model

    @model.setter
    def model(self, value: StructuredModel) -> None:
        self.state.model = value

    @property
    def results(self) -> list[dict[str, Any]]:
        return self.state.results

    @property
    def deferred_operations(self) -> list[tuple[int, dict[str, Any]]]:
        return self.state.deferred_operations

    def reject_operation(
        self,
        sequence: int,
        operation: dict[str, Any],
        reason: str,
        *,
        retry_of: int | None = None,
    ) -> None:
        self.state.reject_operation(sequence, operation, reason, retry_of=retry_of)

    def apply_operation(self, sequence: int, operation: dict[str, Any], *, retry_of: int | None = None) -> None:
        emit_operation_candidate(
            self.emit,
            job_id=self.job_id,
            sequence=sequence,
            operation=operation,
            retry_of=retry_of,
        )
        normalized_operation = normalized_operation_signature_payload(
            operation,
            name_policy=self.name_policy,
        )
        operation_name = str((normalized_operation or {}).get("op") or "").strip()
        if self.allowed_ops and operation_name not in self.allowed_ops:
            self.reject_operation(
                sequence,
                operation,
                (
                    f"Operation type '{operation_name or '<missing>'}' is not allowed for this correction step. "
                    f"Allowed operation types: {', '.join(sorted(self.allowed_ops))}."
                ),
                retry_of=retry_of,
            )
            return
        guard_reason = self.operation_guard_reason(operation)
        if guard_reason is not None:
            self.reject_operation(sequence, operation, guard_reason, retry_of=retry_of)
            return
        if retry_of is None:
            if self.queue.queue_removal_if_needed(
                normalized_operation=normalized_operation,
                sequence=sequence,
                operation=operation,
                emit=self.emit,
                job_id=self.job_id,
            ):
                return
            conflict_reason = self.queue.relationship_conflict_reason(sequence, operation)
            if conflict_reason is not None:
                self.reject_operation(sequence, operation, conflict_reason, retry_of=retry_of)
                return
            self.queue.record_batch_operation(sequence, operation)
        self.state.apply_patch_operation(
            sequence,
            operation,
            retry_of=retry_of,
            summary_prefix="Correction patch operation",
        )

    def apply_queued_relationship_removal(self, sequence: int, operation: dict[str, Any]) -> None:
        guard_reason = self.operation_guard_reason(operation)
        if guard_reason is not None:
            self.reject_operation(sequence, operation, guard_reason)
            return
        conflict_reason = self.queue.relationship_conflict_reason(sequence, operation)
        if conflict_reason is not None:
            self.reject_operation(sequence, operation, conflict_reason)
            return
        self.queue.record_batch_operation(sequence, operation)
        self.state.apply_patch_operation(
            sequence,
            operation,
            summary_prefix="Queued relationship removal",
            track_deferred=False,
        )

    def retry_deferred_operations(self) -> None:
        if not self.deferred_operations:
            return
        pending = list(self.deferred_operations)
        self.deferred_operations.clear()
        for original_sequence, operation in pending:
            retry_sequence = len(self.results) + 1
            self.apply_operation(retry_sequence, operation, retry_of=original_sequence)
            if self.results and self.results[-1]["sequence"] == retry_sequence:
                status = str((self.results[-1].get("result") or {}).get("status") or "")
                if status == "deferred":
                    self.deferred_operations.append((original_sequence, operation))

    def apply_queued_attribute_removal(self, sequence: int, operation: dict[str, Any]) -> None:
        blocked_reason = attribute_remove_blocked_by_deferred_relationship_reason(
            sequence,
            operation,
            self.deferred_operations,
            name_policy=self.name_policy,
        )
        if blocked_reason is not None:
            self.reject_operation(sequence, operation, blocked_reason)
            return
        guard_reason = self.operation_guard_reason(operation)
        if guard_reason is not None:
            self.reject_operation(sequence, operation, guard_reason)
            return
        self.queue.record_batch_operation(sequence, operation)
        self.state.apply_patch_operation(
            sequence,
            operation,
            summary_prefix="Queued attribute removal",
            track_deferred=False,
        )

    def apply_operations(self, operations: list[dict[str, Any]]) -> CorrectionPatchApplicationResult:
        for sequence, operation in enumerate(operations, start=1):
            self.apply_operation(sequence, operation)

        for sequence, operation in list(self.queue.queued_relationship_removals):
            self.apply_queued_relationship_removal(sequence, operation)

        self.retry_deferred_operations()

        for sequence, operation in list(self.queue.queued_attribute_removals):
            self.apply_queued_attribute_removal(sequence, operation)

        return self.state.to_result()


def apply_correction_patch_operations(
    *,
    job_id: str,
    model: StructuredModel,
    specification: str,
    operations: list[dict[str, Any]],
    allowed_ops: set[str],
    emit: Callable[[str, dict[str, Any]], None],
    operation_guard: CorrectionOperationGuard | None = None,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> CorrectionPatchApplicationResult:
    return CorrectionPatchBatchApplier(
        job_id=job_id,
        model=model,
        specification=specification,
        allowed_ops=allowed_ops,
        emit=emit,
        operation_guard=operation_guard,
        name_policy=name_policy,
    ).apply_operations(operations)


__all__ = [
    "CorrectionPatchApplicationResult",
    "CorrectionPatchBatchApplier",
    "apply_correction_patch_operations",
]
