from __future__ import annotations

from typing import Any

PATCH_APPLICATION_FOCUS = "Apply structured patch operation."


def accepted_operation_entry(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"op": result.get("op"), "result": result}]


def rejected_operation_entry(
    operation: dict[str, Any],
    reason: str | None,
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    return [{"op": operation, "error": reason, "result": result}]


def accepted_operation_history_record(sequence: int, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "iteration": 4,
        "batch_attempt": sequence,
        "accepted": accepted_operation_entry(result),
        "rejected": [],
        "focus": PATCH_APPLICATION_FOCUS,
        "feedback": "",
    }


def rejected_operation_history_record(
    sequence: int,
    operation: dict[str, Any],
    reason: str | None,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "iteration": 4,
        "batch_attempt": sequence,
        "accepted": [],
        "rejected": rejected_operation_entry(operation, reason, result),
        "focus": PATCH_APPLICATION_FOCUS,
        "feedback": str(reason or ""),
    }


def deferred_operation_history_record(sequence: int, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "iteration": 4,
        "batch_attempt": sequence,
        "accepted": [],
        "rejected": [],
        "deferred": [{"op": result.get("op"), "result": result}],
        "focus": PATCH_APPLICATION_FOCUS,
        "feedback": str(result.get("reason") or "Operation remains deferred."),
    }


def rejected_operation_result(sequence: int, operation: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "status": "rejected",
        "op": operation,
        "sequence": sequence,
        "reason": reason,
    }


def deferred_operation_entry(sequence: int, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "op": result.get("op"),
        "reason": result.get("reason"),
        "missing_entities": result.get("missing_entities", []),
        "missing_relationships": result.get("missing_relationships", []),
        "blocking_children": result.get("blocking_children", []),
        "blocking_relationships": result.get("blocking_relationships", []),
    }


def operation_applied_payload(
    *,
    status: str,
    result: dict[str, Any],
    summary: str,
    accepted: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": "incrementalOpApplier",
        "status": status,
        "result": result,
        "summary": summary,
    }
    if accepted is not None:
        payload["accepted"] = accepted
    return payload


def operation_candidate_payload(sequence: int, operation: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": "patchOperationClerk",
        "sequence": sequence,
        "operation": operation,
        "summary": (
            f"Structured patch operation candidate {sequence}: "
            f"{operation.get('op') or operation.get('operation') or '<missing>'}."
        ),
    }


def operation_queued_payload(sequence: int, operation: dict[str, Any], summary: str) -> dict[str, Any]:
    return {
        "agent_id": "incrementalOpApplier",
        "sequence": sequence,
        "operation": operation,
        "summary": summary,
    }


__all__ = [
    "accepted_operation_entry",
    "accepted_operation_history_record",
    "deferred_operation_entry",
    "deferred_operation_history_record",
    "operation_applied_payload",
    "operation_candidate_payload",
    "operation_queued_payload",
    "rejected_operation_entry",
    "rejected_operation_history_record",
    "rejected_operation_result",
]
