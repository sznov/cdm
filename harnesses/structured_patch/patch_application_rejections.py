from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from harnesses.structured_patch.patch_application_records import (
    operation_applied_payload,
    rejected_operation_history_record,
    rejected_operation_result,
)

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


async def reject_operation(
    *,
    sequence: int,
    operation: dict[str, Any],
    reason: str,
    rejected_operations: list[dict[str, Any]],
    operation_history: list[dict[str, Any]],
    emit: EmitCallback,
    retry_of: int | None = None,
) -> None:
    result = rejected_operation_result(sequence, operation, reason)
    if retry_of is not None:
        result["retry_of"] = retry_of
        result["deferred_retry"] = True
    rejected_operations.append(result)
    operation_history.append(rejected_operation_history_record(sequence, operation, reason, result))
    await emit(
        "structured_patch_operation_applied",
        operation_applied_payload(
            status="rejected",
            result=result,
            summary=reason,
        ),
    )


__all__ = ["reject_operation"]
