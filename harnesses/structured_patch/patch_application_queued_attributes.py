from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.decision_interactions import mark_equivalent_decision_patches_resolved
from harnesses.structured_patch.patch_application_guards import reject_if_hard_hierarchy_issue
from harnesses.structured_patch.patch_application_queued_results import (
    emit_queued_removal_accepted,
    emit_queued_removal_already_satisfied,
    emit_queued_removal_rejected,
)
from harnesses.structured_patch.patch_application_queued_types import QueuedRemovalApplicationResult
from harnesses.structured_patch.patch_application_rejections import reject_operation
from harnesses.structured_patch.patch_operation_apply import apply_structured_patch_operation
from harnesses.structured_patch.patch_signatures import (
    attribute_remove_blocked_by_deferred_relationship_reason,
)
from core.schemas import StructuredModel

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
SnapshotCallback = Callable[[StructuredModel, str, dict[str, Any] | None], Awaitable[None]]


async def apply_queued_attribute_removals(
    *,
    model: StructuredModel,
    decision_patches: list[dict[str, Any]],
    batch_operations: list[tuple[int, dict[str, Any]]],
    queued_attribute_removals: list[tuple[int, dict[str, Any]]],
    deferred_operations: list[dict[str, Any]],
    applied_operations: list[dict[str, Any]],
    rejected_operations: list[dict[str, Any]],
    already_satisfied_operations: list[dict[str, Any]],
    operation_history: list[dict[str, Any]],
    emit: EmitCallback,
    emit_partial_snapshot: SnapshotCallback,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> QueuedRemovalApplicationResult:
    if not queued_attribute_removals:
        return QueuedRemovalApplicationResult(model=model, decision_patches=decision_patches)
    queued = list(queued_attribute_removals)
    queued_attribute_removals.clear()
    for sequence, operation in queued:
        blocked_reason = attribute_remove_blocked_by_deferred_relationship_reason(
            sequence,
            operation,
            deferred_operations,
            name_policy=name_policy,
        )
        if blocked_reason is not None:
            await reject_operation(
                sequence=sequence,
                operation=operation,
                reason=blocked_reason,
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
            decision_patches = mark_equivalent_decision_patches_resolved(
                decision_patches,
                operation,
                status="resolved",
                reason="An equivalent operation was applied to the model.",
                name_policy=name_policy,
            )
            await emit_queued_removal_accepted(
                label="attribute removal",
                sequence=sequence,
                result=result,
                model=model,
                applied_operations=applied_operations,
                operation_history=operation_history,
                emit=emit,
                emit_partial_snapshot=emit_partial_snapshot,
            )
        elif status == "already_satisfied":
            decision_patches = mark_equivalent_decision_patches_resolved(
                decision_patches,
                operation,
                status="obsolete",
                reason="The model already satisfied an equivalent pending operation.",
                name_policy=name_policy,
            )
            await emit_queued_removal_already_satisfied(
                label="attribute removal",
                sequence=sequence,
                result=result,
                already_satisfied_operations=already_satisfied_operations,
                emit=emit,
            )
        else:
            await emit_queued_removal_rejected(
                label="attribute removal",
                sequence=sequence,
                result=result,
                rejected_operations=rejected_operations,
                operation_history=operation_history,
                emit=emit,
            )
    return QueuedRemovalApplicationResult(model=model, decision_patches=decision_patches)


__all__ = ["apply_queued_attribute_removals"]
