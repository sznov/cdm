from __future__ import annotations

from collections.abc import Callable
from typing import Any

from harnesses.structured_patch.patch_signatures import relationship_add_remove_conflict_reason
from backend.services.correction_patch_application_events import emit_operation_queued
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)


RELATIONSHIP_REMOVAL_QUEUE_SUMMARY = (
    "Queued relationship removal until the correction patch batch is complete so "
    "remove-and-readd replacement patterns cannot delete relationships."
)
ATTRIBUTE_REMOVAL_QUEUE_SUMMARY = (
    "Queued attribute removal until the correction patch batch is complete so "
    "replacement entities and relationships can be validated first."
)


class CorrectionPatchOperationQueue:
    def __init__(
        self,
        *,
        name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
    ) -> None:
        self.name_policy = name_policy
        self.batch_operations: list[tuple[int, dict[str, Any]]] = []
        self.queued_relationship_removals: list[tuple[int, dict[str, Any]]] = []
        self.queued_attribute_removals: list[tuple[int, dict[str, Any]]] = []

    def queue_removal_if_needed(
        self,
        *,
        normalized_operation: dict[str, Any] | None,
        sequence: int,
        operation: dict[str, Any],
        emit: Callable[[str, dict[str, Any]], None],
        job_id: str,
    ) -> bool:
        operation_name = str((normalized_operation or {}).get("op") or "").strip()
        if operation_name == "removeRelationship":
            self.queued_relationship_removals.append((sequence, operation))
            emit_operation_queued(
                emit,
                job_id=job_id,
                sequence=sequence,
                operation=operation,
                summary=RELATIONSHIP_REMOVAL_QUEUE_SUMMARY,
            )
            return True
        if operation_name == "removeAttribute":
            self.queued_attribute_removals.append((sequence, operation))
            emit_operation_queued(
                emit,
                job_id=job_id,
                sequence=sequence,
                operation=operation,
                summary=ATTRIBUTE_REMOVAL_QUEUE_SUMMARY,
            )
            return True
        return False

    def relationship_conflict_reason(self, sequence: int, operation: dict[str, Any]) -> str | None:
        for prior_sequence, prior_operation in self.batch_operations:
            conflict_reason = relationship_add_remove_conflict_reason(
                prior_sequence,
                prior_operation,
                sequence,
                operation,
                name_policy=self.name_policy,
            )
            if conflict_reason is not None:
                return conflict_reason
        return None

    def record_batch_operation(self, sequence: int, operation: dict[str, Any]) -> None:
        self.batch_operations.append((sequence, operation))


__all__ = [
    "ATTRIBUTE_REMOVAL_QUEUE_SUMMARY",
    "CorrectionPatchOperationQueue",
    "RELATIONSHIP_REMOVAL_QUEUE_SUMMARY",
]
