from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import json
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.decision_interactions import pending_decision_operation_interaction
from harnesses.structured_patch.correction_policy import CorrectionOperationGuard
from harnesses.structured_patch.patch_parse_contract import canonical_structured_patch_op_name
from harnesses.structured_patch.patch_application_deferred import (
    operation_payload_signature,
    retry_deferred_patch_operations,
)
from harnesses.structured_patch.patch_application_immediate import apply_immediate_patch_operation
from harnesses.structured_patch.patch_application_pending_decisions import (
    reject_pending_decision_operation,
)
from harnesses.structured_patch.patch_application_records import (
    deferred_operation_history_record,
    operation_candidate_payload,
)
from harnesses.structured_patch.patch_application_conflicts import relationship_conflict_reason
from harnesses.structured_patch.patch_application_queueing import queue_delayed_removal_if_needed
from harnesses.structured_patch.patch_application_queued_removals import (
    apply_queued_attribute_removals as apply_queued_attribute_removals_batch,
    apply_queued_relationship_removals as apply_queued_relationship_removals_batch,
)
from harnesses.structured_patch.patch_application_rejections import reject_operation as reject_patch_operation
from core.schemas import StructuredModel

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
SnapshotCallback = Callable[[StructuredModel, str, dict[str, Any] | None], Awaitable[None]]


@dataclass(slots=True)
class StructuredPatchApplicationState:
    model: StructuredModel
    decision_patches: list[dict[str, Any]]
    applied_operations: list[dict[str, Any]]
    rejected_operations: list[dict[str, Any]]
    already_satisfied_operations: list[dict[str, Any]]
    deferred_operations: list[dict[str, Any]]
    operation_history: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class StructuredPatchApplicationCallbacks:
    emit: EmitCallback
    emit_partial_snapshot: SnapshotCallback


@dataclass(frozen=True, slots=True)
class StructuredPatchApplicationPolicy:
    operation_guard: CorrectionOperationGuard | None = None
    validate_deferred_retries: bool = False
    preserve_provisional_identifier: bool = False
    allowed_ops: frozenset[str] = frozenset()
    initial_sequence: int = 0
    last_deferred_retry_fingerprint: str | None = None
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY


class StructuredPatchBatchApplier:
    def __init__(
        self,
        *,
        specification: str,
        state: StructuredPatchApplicationState,
        callbacks: StructuredPatchApplicationCallbacks,
        policy: StructuredPatchApplicationPolicy | None = None,
    ) -> None:
        resolved_policy = policy or StructuredPatchApplicationPolicy()
        self.specification = specification
        self.model = state.model
        self.decision_patches = state.decision_patches
        self.applied_operations = state.applied_operations
        self.rejected_operations = state.rejected_operations
        self.already_satisfied_operations = state.already_satisfied_operations
        self.deferred_operations = state.deferred_operations
        self.operation_history = state.operation_history
        self.emit = callbacks.emit
        self.emit_partial_snapshot = callbacks.emit_partial_snapshot
        self.operation_guard = resolved_policy.operation_guard
        self.validate_deferred_retries = resolved_policy.validate_deferred_retries
        self.preserve_provisional_identifier = resolved_policy.preserve_provisional_identifier
        self.allowed_ops = set(resolved_policy.allowed_ops)
        self.parsed_operation_count = max(0, int(resolved_policy.initial_sequence))
        self.last_deferred_retry_fingerprint = resolved_policy.last_deferred_retry_fingerprint
        self.name_policy = resolved_policy.name_policy
        self.batch_operations: list[tuple[int, dict[str, Any]]] = []
        self.queued_relationship_removals: list[tuple[int, dict[str, Any]]] = []
        self.queued_attribute_removals: list[tuple[int, dict[str, Any]]] = []

    def operation_count(self) -> int:
        return self.parsed_operation_count

    def _deferred_retry_input_fingerprint(self) -> str:
        return json.dumps(
            {
                "model": self.model.model_dump(mode="json"),
                "operations": [
                    operation_payload_signature(
                        item.get("op"),
                        name_policy=self.name_policy,
                    )
                    for item in self.deferred_operations
                ],
            },
            sort_keys=True,
            ensure_ascii=False,
        )

    async def retry_deferred_operations(self) -> None:
        if not self.validate_deferred_retries:
            self.model = await retry_deferred_patch_operations(
                model=self.model,
                deferred_operations=self.deferred_operations,
                applied_operations=self.applied_operations,
                rejected_operations=self.rejected_operations,
                already_satisfied_operations=self.already_satisfied_operations,
                emit=self.emit,
                emit_partial_snapshot=self.emit_partial_snapshot,
                name_policy=self.name_policy,
            )
            return

        if not self.deferred_operations:
            return
        retry_fingerprint = self._deferred_retry_input_fingerprint()
        if retry_fingerprint == self.last_deferred_retry_fingerprint:
            return
        self.last_deferred_retry_fingerprint = retry_fingerprint

        permitted_deferred_operations: list[dict[str, Any]] = []
        for deferred in self.deferred_operations:
            operation = deferred.get("op") if isinstance(deferred.get("op"), dict) else None
            if operation is None:
                permitted_deferred_operations.append(deferred)
                continue
            retry_of = int(deferred.get("retry_of") or deferred.get("sequence") or 0)
            self.parsed_operation_count = max(self.parsed_operation_count, retry_of)
            self.parsed_operation_count += 1
            retry_sequence = self.parsed_operation_count
            candidate_payload = operation_candidate_payload(retry_sequence, operation)
            candidate_payload.update(
                {
                    "retry_of": retry_of,
                    "deferred_retry": True,
                }
            )
            await self.emit("structured_patch_operation_candidate", candidate_payload)
            pending_interaction = pending_decision_operation_interaction(
                operation,
                self.decision_patches,
                name_policy=self.name_policy,
            )
            if pending_interaction is not None:
                self.decision_patches = await reject_pending_decision_operation(
                    sequence=retry_sequence,
                    operation=operation,
                    pending_interaction=pending_interaction,
                    decision_patches=self.decision_patches,
                    rejected_operations=self.rejected_operations,
                    operation_history=self.operation_history,
                    emit=self.emit,
                    retry_of=retry_of,
                    name_policy=self.name_policy,
                )
                continue
            if self.operation_guard is not None:
                guard_reason = self.operation_guard(operation, self.model, self.specification)
                if guard_reason is not None:
                    await self._reject_operation(
                        retry_sequence,
                        operation,
                        guard_reason,
                        retry_of=retry_of,
                    )
                    continue
            permitted_deferred_operations.append(
                {
                    **deferred,
                    "retry_of": retry_of,
                    "retry_sequence": retry_sequence,
                }
            )
        self.deferred_operations[:] = permitted_deferred_operations
        deferred_attempt_results: list[dict[str, Any]] = []
        self.model = await retry_deferred_patch_operations(
            model=self.model,
            deferred_operations=self.deferred_operations,
            applied_operations=self.applied_operations,
            rejected_operations=self.rejected_operations,
            already_satisfied_operations=self.already_satisfied_operations,
            emit=self.emit,
            emit_partial_snapshot=self.emit_partial_snapshot,
            deferred_attempt_results=deferred_attempt_results,
            name_policy=self.name_policy,
        )
        for attempt_result in deferred_attempt_results:
            if not any(
                isinstance(entry, dict) and entry.get("result") is attempt_result
                for history_item in self.operation_history
                for entry in history_item.get("deferred") or []
            ):
                self.operation_history.append(
                    deferred_operation_history_record(
                        int(attempt_result.get("sequence") or self.parsed_operation_count),
                        attempt_result,
                    )
                )
        if not self.deferred_operations:
            self.last_deferred_retry_fingerprint = None

    async def apply_parsed_operation(self, operation: dict[str, Any]) -> None:
        self.parsed_operation_count += 1
        sequence = self.parsed_operation_count
        await self.emit(
            "structured_patch_operation_candidate",
            operation_candidate_payload(sequence, operation),
        )
        pending_interaction = pending_decision_operation_interaction(
            operation,
            self.decision_patches,
            name_policy=self.name_policy,
        )
        if pending_interaction is not None:
            self.decision_patches = await reject_pending_decision_operation(
                sequence=sequence,
                operation=operation,
                pending_interaction=pending_interaction,
                decision_patches=self.decision_patches,
                rejected_operations=self.rejected_operations,
                operation_history=self.operation_history,
                emit=self.emit,
                name_policy=self.name_policy,
            )
            return

        operation_name = canonical_structured_patch_op_name(
            operation.get("op") or operation.get("operation") or operation.get("type")
        )
        if self.allowed_ops and operation_name not in self.allowed_ops:
            await self._reject_operation(
                sequence,
                operation,
                (
                    f"Operation type '{operation_name or '<missing>'}' is not allowed for this correction step. "
                    f"Allowed operation types: {', '.join(sorted(self.allowed_ops))}."
                ),
            )
            return

        if self.operation_guard is not None:
            guard_reason = self.operation_guard(operation, self.model, self.specification)
            if guard_reason is not None:
                await self._reject_operation(sequence, operation, guard_reason)
                return

        if await queue_delayed_removal_if_needed(
            sequence=sequence,
            operation=operation,
            queued_relationship_removals=self.queued_relationship_removals,
            queued_attribute_removals=self.queued_attribute_removals,
            emit=self.emit,
            name_policy=self.name_policy,
        ):
            return
        conflict_reason = relationship_conflict_reason(
            self.batch_operations,
            sequence,
            operation,
            name_policy=self.name_policy,
        )
        if conflict_reason is not None:
            await self._reject_operation(sequence, operation, conflict_reason)
            return

        self.batch_operations.append((sequence, operation))
        result = await apply_immediate_patch_operation(
            sequence=sequence,
            operation=operation,
            model=self.model,
            decision_patches=self.decision_patches,
            applied_operations=self.applied_operations,
            rejected_operations=self.rejected_operations,
            already_satisfied_operations=self.already_satisfied_operations,
            deferred_operations=self.deferred_operations,
            operation_history=self.operation_history,
            emit=self.emit,
            emit_partial_snapshot=self.emit_partial_snapshot,
            preserve_provisional_identifier=self.preserve_provisional_identifier,
            name_policy=self.name_policy,
        )
        self.model = result.model
        self.decision_patches = result.decision_patches
        if result.retry_deferred:
            await self.retry_deferred_operations()

    async def apply_queued_relationship_removals(self) -> None:
        if self.operation_guard is not None and self.queued_relationship_removals:
            permitted_removals: list[tuple[int, dict[str, Any]]] = []
            for sequence, operation in self.queued_relationship_removals:
                guard_reason = self.operation_guard(operation, self.model, self.specification)
                if guard_reason is None:
                    permitted_removals.append((sequence, operation))
                else:
                    await self._reject_operation(sequence, operation, guard_reason)
            self.queued_relationship_removals = permitted_removals
        result = await apply_queued_relationship_removals_batch(
            model=self.model,
            decision_patches=self.decision_patches,
            batch_operations=self.batch_operations,
            queued_relationship_removals=self.queued_relationship_removals,
            deferred_operations=self.deferred_operations,
            applied_operations=self.applied_operations,
            rejected_operations=self.rejected_operations,
            already_satisfied_operations=self.already_satisfied_operations,
            operation_history=self.operation_history,
            emit=self.emit,
            emit_partial_snapshot=self.emit_partial_snapshot,
            name_policy=self.name_policy,
        )
        self.model = result.model
        self.decision_patches = result.decision_patches

    async def apply_queued_attribute_removals(self) -> None:
        if self.operation_guard is not None and self.queued_attribute_removals:
            permitted_removals: list[tuple[int, dict[str, Any]]] = []
            for sequence, operation in self.queued_attribute_removals:
                guard_reason = self.operation_guard(operation, self.model, self.specification)
                if guard_reason is None:
                    permitted_removals.append((sequence, operation))
                else:
                    await self._reject_operation(sequence, operation, guard_reason)
            self.queued_attribute_removals = permitted_removals
        result = await apply_queued_attribute_removals_batch(
            model=self.model,
            decision_patches=self.decision_patches,
            batch_operations=self.batch_operations,
            queued_attribute_removals=self.queued_attribute_removals,
            deferred_operations=self.deferred_operations,
            applied_operations=self.applied_operations,
            rejected_operations=self.rejected_operations,
            already_satisfied_operations=self.already_satisfied_operations,
            operation_history=self.operation_history,
            emit=self.emit,
            emit_partial_snapshot=self.emit_partial_snapshot,
            name_policy=self.name_policy,
        )
        self.model = result.model
        self.decision_patches = result.decision_patches

    async def _reject_operation(
        self,
        sequence: int,
        operation: dict[str, Any],
        reason: str,
        *,
        retry_of: int | None = None,
    ) -> None:
        await reject_patch_operation(
            sequence=sequence,
            operation=operation,
            reason=reason,
            rejected_operations=self.rejected_operations,
            operation_history=self.operation_history,
            emit=self.emit,
            retry_of=retry_of,
        )


__all__ = [
    "StructuredPatchApplicationCallbacks",
    "StructuredPatchApplicationPolicy",
    "StructuredPatchApplicationState",
    "StructuredPatchBatchApplier",
]
