from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_application_conflicts import relationship_conflict_reason
from harnesses.structured_patch.patch_application_guards import reject_if_hard_hierarchy_issue
from harnesses.structured_patch.patch_application_queued_results import (
    emit_queued_removal_accepted,
    emit_queued_removal_already_satisfied,
    emit_queued_removal_rejected,
)
from harnesses.structured_patch.patch_application_queued_types import QueuedRemovalApplicationResult
from harnesses.structured_patch.patch_application_rejections import reject_operation
from harnesses.structured_patch.patch_operation_apply import apply_structured_patch_operation
from core.schemas import StructuredModel

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
SnapshotCallback = Callable[[StructuredModel, str, dict[str, Any] | None], Awaitable[None]]


async def apply_queued_relationship_removals(
    *,
    model: StructuredModel,
    decision_patches: list[dict[str, Any]],
    batch_operations: list[tuple[int, dict[str, Any]]],
    queued_relationship_removals: list[tuple[int, dict[str, Any]]],
    deferred_operations: list[dict[str, Any]],
    applied_operations: list[dict[str, Any]],
    rejected_operations: list[dict[str, Any]],
    already_satisfied_operations: list[dict[str, Any]],
    operation_history: list[dict[str, Any]],
    emit: EmitCallback,
    emit_partial_snapshot: SnapshotCallback,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> QueuedRemovalApplicationResult:
    if not queued_relationship_removals:
        return QueuedRemovalApplicationResult(model=model, decision_patches=decision_patches)
    queued = list(queued_relationship_removals)
    queued_relationship_removals.clear()
    for sequence, operation in queued:
        conflict_reason = relationship_conflict_reason(
            batch_operations,
            sequence,
            operation,
            name_policy=name_policy,
        )
        if conflict_reason is not None:
            await reject_operation(
                sequence=sequence,
                operation=operation,
                reason=conflict_reason,
                rejected_operations=rejected_operations,
                operation_history=operation_history,
                emit=emit,
            )
            continue
        batch_operations.append((sequence, operation))
        after, result = apply_structured_patch_operation(
            model,
            operation,
            name_policy=name_policy,
        )
        result = {**result, "sequence": sequence}
        status = result["status"]
        if status == "accepted":
            if await reject_if_hard_hierarchy_issue(
                model=model,
                after=after,
                sequence=sequence,
                operation=operation,
                deferred_operations=deferred_operations,
                result=result,
                rejected_operations=rejected_operations,
                operation_history=operation_history,
                emit=emit,
                name_policy=name_policy,
            ):
                continue
            model = after
            await emit_queued_removal_accepted(
                label="relationship removal",
                sequence=sequence,
                result=result,
                model=model,
                applied_operations=applied_operations,
                operation_history=operation_history,
                emit=emit,
                emit_partial_snapshot=emit_partial_snapshot,
            )
        elif status == "already_satisfied":
            await emit_queued_removal_already_satisfied(
                label="relationship removal",
                sequence=sequence,
                result=result,
                already_satisfied_operations=already_satisfied_operations,
                emit=emit,
            )
        else:
            await emit_queued_removal_rejected(
                label="relationship removal",
                sequence=sequence,
                result=result,
                rejected_operations=rejected_operations,
                operation_history=operation_history,
                emit=emit,
            )
    return QueuedRemovalApplicationResult(model=model, decision_patches=decision_patches)


__all__ = ["apply_queued_relationship_removals"]
