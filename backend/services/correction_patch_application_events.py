from __future__ import annotations

from collections.abc import Callable
from typing import Any


def rejected_operation_result(operation: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"status": "rejected", "op": operation, "reason": reason}


def operation_result_payload(
    *,
    sequence: int,
    operation: dict[str, Any],
    result: dict[str, Any],
    retry_of: int | None = None,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "retry_of_sequence": retry_of,
        "operation": operation,
        "result": result,
    }


def emit_operation_candidate(
    emit: Callable[[str, dict[str, Any]], None],
    *,
    job_id: str,
    sequence: int,
    operation: dict[str, Any],
    retry_of: int | None = None,
) -> None:
    label = f"{sequence}" if retry_of is None else f"{retry_of} retry"
    emit(
        "structured_patch_operation_candidate",
        {
            "job_id": job_id,
            "agent_id": "patchOperationClerk",
            "sequence": sequence,
            "retry_of_sequence": retry_of,
            "operation": operation,
            "summary": f"Correction patch operation {label} parsed.",
        },
    )


def emit_operation_queued(
    emit: Callable[[str, dict[str, Any]], None],
    *,
    job_id: str,
    sequence: int,
    operation: dict[str, Any],
    summary: str,
) -> None:
    emit(
        "structured_patch_operation_queued",
        {
            "job_id": job_id,
            "agent_id": "incrementalOpApplier",
            "sequence": sequence,
            "operation": operation,
            "summary": summary,
        },
    )


def emit_operation_applied(
    emit: Callable[[str, dict[str, Any]], None],
    *,
    job_id: str,
    sequence: int,
    result: dict[str, Any],
    status: str,
    summary: str,
    retry_of: int | None = None,
) -> None:
    emit(
        "structured_patch_operation_applied",
        {
            "job_id": job_id,
            "agent_id": "incrementalOpApplier",
            "sequence": sequence,
            "retry_of_sequence": retry_of,
            "status": status,
            "result": result,
            "summary": summary,
        },
    )


__all__ = [
    "emit_operation_applied",
    "emit_operation_candidate",
    "emit_operation_queued",
    "operation_result_payload",
    "rejected_operation_result",
]
