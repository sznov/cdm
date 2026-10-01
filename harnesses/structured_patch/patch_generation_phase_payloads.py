from __future__ import annotations

from typing import Any

from core.model_client import ChatMessage


def patch_operation_prompt_payload(
    *,
    patch_clerk_system_prompt: str,
    patch_messages: list[ChatMessage],
) -> dict[str, Any]:
    return {
        "agent_id": "patchOperationClerk",
        "title": "Patch operation clerk prompt",
        "summary": "Coverage findings and current model resolved into an operation-patch prompt.",
        "system_prompt": patch_clerk_system_prompt,
        "messages": [dict(message) for message in patch_messages],
    }


def patch_operation_generation_start_payload() -> dict[str, Any]:
    return {
        "agent_id": "patchOperationClerk",
        "iteration": 4,
        "summary": "Generating structured patch operations.",
    }


def patch_operation_generation_delta_payload(*, delta: str) -> dict[str, Any]:
    return {"agent_id": "patchOperationClerk", "delta": delta}


def patch_operation_parse_error_payload(*, error: str) -> dict[str, Any]:
    return {
        "agent_id": "patchOperationClerk",
        "error": error,
        "summary": error,
    }


def patch_operation_generation_done_payload(
    *,
    raw_output: str,
    parsed_operation_count: int,
    stream_parse_errors: list[str],
    repair_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "agent_id": "patchOperationClerk",
        "raw_output": raw_output,
        "operation_count": parsed_operation_count,
        "parse_errors": stream_parse_errors,
        "repair_reports": repair_reports,
        "summary": f"Patch operation clerk produced {parsed_operation_count} parsed operation(s).",
    }


def patch_operation_history_record(
    *,
    parsed_operation_count: int,
    stream_parse_errors: list[str],
) -> dict[str, Any]:
    return {
        "iteration": 4,
        "batch_attempt": 1,
        "accepted": [{"op": "PATCH_OPERATION_CLERK", "operation_count": parsed_operation_count}],
        "rejected": [{"op": "PATCH_OPERATION_PARSE", "error": error} for error in stream_parse_errors],
        "focus": "Generate and apply structured patch operations.",
        "feedback": "\n".join(stream_parse_errors),
    }


__all__ = [
    "patch_operation_generation_delta_payload",
    "patch_operation_generation_done_payload",
    "patch_operation_generation_start_payload",
    "patch_operation_history_record",
    "patch_operation_parse_error_payload",
    "patch_operation_prompt_payload",
]
