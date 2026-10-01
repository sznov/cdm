from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.decision_merge import merge_decision_patches
from harnesses.structured_patch.decision_interactions import decision_patch_from_blocked_operation
from harnesses.structured_patch.patch_application_records import (
    operation_applied_payload,
    rejected_operation_history_record,
)

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


async def reject_pending_decision_operation(
    *,
    sequence: int,
    operation: dict[str, Any],
    pending_interaction: dict[str, Any],
    decision_patches: list[dict[str, Any]],
    rejected_operations: list[dict[str, Any]],
    operation_history: list[dict[str, Any]],
    emit: EmitCallback,
    retry_of: int | None = None,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    blocking_patch = pending_interaction["patch"]
    interaction_kind = pending_interaction["kind"]
    result = {
        "status": "blocked_pending_decision",
        "op": operation,
        "sequence": sequence,
        "reason": (
            "Operation overlaps an unresolved decision patch and was not applied automatically."
            if interaction_kind == "overlap"
            else "Operation is equivalent to an unresolved decision patch and was not applied automatically."
        ),
        "decision_patch_id": blocking_patch.get("id"),
        "decision_patch_title": blocking_patch.get("title"),
        "interaction": interaction_kind,
    }
    if retry_of is not None:
        result["retry_of"] = retry_of
        result["deferred_retry"] = True
    if interaction_kind == "overlap":
        decision_patches = merge_decision_patches(
            decision_patches,
            [
                decision_patch_from_blocked_operation(
                    operation,
                    blocking_patch=blocking_patch,
                    interaction_kind=interaction_kind,
                    name_policy=name_policy,
                )
            ],
            name_policy=name_policy,
        )
        await emit(
            "decision_patches",
            {
                "agent_id": "incrementalOpApplier",
                "decision_patches": decision_patches,
                "summary": "Overlapping patch operation was routed to the decision system.",
            },
        )
    rejected_operations.append(result)
    operation_history.append(rejected_operation_history_record(sequence, operation, result["reason"], result))
    await emit(
        "structured_patch_operation_applied",
        operation_applied_payload(
            status=result["status"],
            result=result,
            summary=result["reason"],
        ),
    )
    return decision_patches


__all__ = ["reject_pending_decision_operation"]
