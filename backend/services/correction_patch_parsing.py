from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.persistence.session_chat import append_session_chat_message
from harnesses.structured_patch.patch_parse_stream import parse_structured_patch_operations
from core.schemas import StructuredOutputError
from backend.services.async_file_work import run_thread_to_completion
from backend.services.trace_event_recorder import AsyncEventEmitter


def parse_correction_patch_operations(raw_output: str, *, max_operations: int | None = None) -> list[dict[str, Any]]:
    operations = parse_structured_patch_operations(raw_output)
    if max_operations is not None:
        return operations[:max_operations]
    return operations


async def correction_patch_parse_error_response(
    *,
    job_id: str,
    raw_output: str,
    error: StructuredOutputError,
    emit: AsyncEventEmitter,
    session_id: str | None,
    sessions_dir: Path,
) -> dict[str, Any]:
    error_text = str(error)
    await emit(
        "structured_patch_operation_parse_error",
        {
            "job_id": job_id,
            "agent_id": "patchOperationClerk",
            "error": error_text,
            "raw_output": raw_output,
            "summary": "Could not parse structured patch operations from correction output.",
        },
    )
    done_payload = {
        "job_id": job_id,
        "accepted_count": 0,
        "changed_count": 0,
        "rejected_count": 1,
        "deferred_count": 0,
        "parse_error": error_text,
        "summary": "Correction produced no applicable patch operations.",
    }
    await run_thread_to_completion(
        append_session_chat_message,
        session_id,
        "assistant",
        done_payload["summary"],
        kind="correction",
        sessions_dir=sessions_dir,
    )
    await emit("correction_patch_chat_done", done_payload, durability="commit")
    return {
        **done_payload,
        "raw_output": raw_output,
        "operations": [],
        "results": [],
    }


__all__ = ["correction_patch_parse_error_response", "parse_correction_patch_operations"]
