from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from harnesses.structured_patch.patch_application_records import (
    accepted_operation_entry,
    accepted_operation_history_record,
    operation_applied_payload,
    rejected_operation_history_record,
)
from core.schemas import StructuredModel

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
SnapshotCallback = Callable[[StructuredModel, str, dict[str, Any] | None], Awaitable[None]]


async def emit_queued_removal_accepted(
    *,
    label: str,
    sequence: int,
    result: dict[str, Any],
    model: StructuredModel,
    applied_operations: list[dict[str, Any]],
    operation_history: list[dict[str, Any]],
    emit: EmitCallback,
    emit_partial_snapshot: SnapshotCallback,
) -> None:
    applied_operations.append(result)
    operation_history.append(accepted_operation_history_record(sequence, result))
    await emit(
        "structured_patch_operation_applied",
        operation_applied_payload(
            status="accepted",
            result=result,
            accepted=accepted_operation_entry(result),
            summary=f"Applied queued {label} {sequence}: {result.get('op', {}).get('op')}.",
        ),
    )
    await emit_partial_snapshot(model, f"Rendered after queued {label} {sequence}.", result)


async def emit_queued_removal_already_satisfied(
    *,
    label: str,
    sequence: int,
    result: dict[str, Any],
    already_satisfied_operations: list[dict[str, Any]],
    emit: EmitCallback,
) -> None:
    already_satisfied_operations.append(result)
    await emit(
        "structured_patch_operation_applied",
        operation_applied_payload(
            status="already_satisfied",
            result=result,
            summary=result.get("reason") or f"Queued {label} {sequence} already satisfied.",
        ),
    )


async def emit_queued_removal_rejected(
    *,
    label: str,
    sequence: int,
    result: dict[str, Any],
    rejected_operations: list[dict[str, Any]],
    operation_history: list[dict[str, Any]],
    emit: EmitCallback,
) -> None:
    rejected_operations.append(result)
    operation_history.append(rejected_operation_history_record(sequence, result.get("op"), result.get("reason"), result))
    await emit(
        "structured_patch_operation_applied",
        operation_applied_payload(
            status="rejected",
            result=result,
            summary=result.get("reason") or f"Rejected queued {label} {sequence}.",
        ),
    )


__all__ = [
    "emit_queued_removal_accepted",
    "emit_queued_removal_already_satisfied",
    "emit_queued_removal_rejected",
]
