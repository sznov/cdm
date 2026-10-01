from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_application_records import (
    operation_applied_payload,
    rejected_operation_history_record,
)
from harnesses.structured_patch.validation import introduced_hard_hierarchy_issue_reason
from core.schemas import StructuredModel

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


async def reject_if_hard_hierarchy_issue(
    *,
    model: StructuredModel,
    after: StructuredModel,
    sequence: int,
    operation: dict[str, Any],
    deferred_operations: list[dict[str, Any]],
    result: dict[str, Any],
    rejected_operations: list[dict[str, Any]],
    operation_history: list[dict[str, Any]],
    emit: EmitCallback,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> bool:
    guard_reason = introduced_hard_hierarchy_issue_reason(
        model,
        after,
        sequence=sequence,
        operation=operation,
        deferred_operations=deferred_operations,
        name_policy=name_policy,
    )
    if guard_reason is None:
        return False

    guarded_result = {**result, "status": "rejected", "reason": guard_reason}
    rejected_operations.append(guarded_result)
    operation_history.append(rejected_operation_history_record(sequence, operation, guard_reason, guarded_result))
    await emit(
        "structured_patch_operation_applied",
        operation_applied_payload(
            status="rejected",
            result=guarded_result,
            summary=guard_reason,
        ),
    )
    return True


__all__ = ["reject_if_hard_hierarchy_issue"]
