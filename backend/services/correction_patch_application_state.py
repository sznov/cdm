from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from harnesses.structured_patch.patch_operation_apply import apply_structured_patch_operation
from core.schemas import StructuredModel
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from backend.services.correction_patch_application_events import (
    emit_operation_applied,
    operation_result_payload,
    rejected_operation_result,
)


@dataclass
class CorrectionPatchApplicationResult:
    model: StructuredModel
    results: list[dict[str, Any]]
    accepted_count: int
    changed_count: int
    rejected_count: int
    deferred_count: int


class CorrectionPatchApplicationState:
    def __init__(
        self,
        *,
        job_id: str,
        model: StructuredModel,
        emit: Callable[[str, dict[str, Any]], None],
        name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
    ) -> None:
        self.job_id = job_id
        self.model = model
        self.emit = emit
        self.name_policy = name_policy
        self.results: list[dict[str, Any]] = []
        self.accepted_count = 0
        self.changed_count = 0
        self.rejected_count = 0
        self.deferred_count = 0
        self.deferred_operations: list[tuple[int, dict[str, Any]]] = []

    def reject_operation(
        self,
        sequence: int,
        operation: dict[str, Any],
        reason: str,
        *,
        retry_of: int | None = None,
    ) -> None:
        self.rejected_count += 1
        result = rejected_operation_result(operation, reason)
        self.results.append(
            operation_result_payload(sequence=sequence, operation=operation, result=result, retry_of=retry_of)
        )
        emit_operation_applied(
            self.emit,
            job_id=self.job_id,
            sequence=sequence,
            retry_of=retry_of,
            status="rejected",
            result=result,
            summary=reason,
        )

    def apply_patch_operation(
        self,
        sequence: int,
        operation: dict[str, Any],
        *,
        retry_of: int | None = None,
        summary_prefix: str = "Correction patch operation",
        track_deferred: bool = True,
    ) -> None:
        after, result = apply_structured_patch_operation(
            self.model,
            operation,
            name_policy=self.name_policy,
        )
        status = str(result.get("status") or "")
        if status == "accepted":
            self.model = after
            self.accepted_count += 1
            self.changed_count += 1
        elif status == "already_satisfied":
            self.accepted_count += 1
        elif status == "deferred" and track_deferred:
            self.deferred_count += 1
            if retry_of is None:
                self.deferred_operations.append((sequence, operation))
        else:
            self.rejected_count += 1
        self.results.append(
            operation_result_payload(sequence=sequence, operation=operation, result=result, retry_of=retry_of)
        )
        emit_operation_applied(
            self.emit,
            job_id=self.job_id,
            sequence=sequence,
            retry_of=retry_of,
            status=status,
            result=result,
            summary=result.get("reason") or f"{summary_prefix} {status or 'processed'}.",
        )

    def to_result(self) -> CorrectionPatchApplicationResult:
        return CorrectionPatchApplicationResult(
            model=self.model,
            results=self.results,
            accepted_count=self.accepted_count,
            changed_count=self.changed_count,
            rejected_count=self.rejected_count,
            deferred_count=self.deferred_count,
        )


__all__ = ["CorrectionPatchApplicationResult", "CorrectionPatchApplicationState"]
