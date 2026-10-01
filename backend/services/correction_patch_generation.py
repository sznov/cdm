from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.model_call_completion import complete_with_logging
from core.model_call_logger import ModelCallLogger
from core.providers.factory import provider_descriptor
from backend.api.models import CorrectionPatchRequest
from backend.persistence.session_chat import append_session_chat_message
from backend.services.async_file_work import run_thread_to_completion
from harnesses.structured_patch.patch_prompts import PATCH_OPERATION_CLERK_SYSTEM_PROMPT
from backend.services.correction_clients import model_call_error_detail
from backend.services.correction_events import CorrectionEventRecorder


@dataclass(slots=True)
class CorrectionPatchGenerationResult:
    raw_output: str
    failure_response: dict[str, Any] | None = None


async def generate_correction_patch_output(
    *,
    job_id: str,
    request: CorrectionPatchRequest,
    provider: str,
    client: Any,
    logger: ModelCallLogger,
    event_recorder: CorrectionEventRecorder,
    emit: Any,
    session_id: str | None,
    sessions_dir: Path,
    user_prompt: str,
    messages: list[dict[str, str]],
    allowed_ops: set[str],
) -> CorrectionPatchGenerationResult:
    await emit(
        "correction_patch_generation_start",
        {
            "job_id": job_id,
            "agent_id": "patchOperationClerk",
            "summary": "Streaming correction patch model output.",
        },
    )

    async def on_correction_token(delta: str) -> None:
        if not delta:
            return
        await event_recorder.emit_delta(
            "correction_patch_generation_delta",
            {
                "job_id": job_id,
                "agent_id": "patchOperationClerk",
                "delta": delta,
            },
        )

    try:
        try:
            supports_streaming = provider_descriptor(provider).supports_streaming
        except ValueError:
            supports_streaming = True
        completion, log_record = await complete_with_logging(
            client=client,
            logger=logger,
            kind="freeform_correction_patch_operation",
            system_prompt=PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
            user_content=user_prompt,
            messages=messages,
            on_token=on_correction_token if supports_streaming else None,
            metadata={
                "source": "freeform_correction_chat",
                "max_operations": request.max_operations,
                "allowed_ops": sorted(allowed_ops) if allowed_ops else None,
            },
        )
        if not supports_streaming and completion.text:
            await on_correction_token(completion.text)
    except asyncio.CancelledError:
        for record_item in logger.records:
            await emit("model_call_log", record_item)
        detail = "Correction patch generation was interrupted before it completed."
        error_payload = {
            "job_id": job_id,
            "agent_id": "patchOperationClerk",
            "error": detail,
            "summary": detail,
        }
        await emit("correction_patch_model_call_error", error_payload)
        done_payload = {
            "job_id": job_id,
            "accepted_count": 0,
            "changed_count": 0,
            "rejected_count": 1,
            "deferred_count": 0,
            "error": detail,
            "interrupted": True,
            "summary": detail,
        }
        await run_thread_to_completion(
            append_session_chat_message,
            session_id,
            "assistant",
            detail,
            kind="correction",
            sessions_dir=sessions_dir,
        )
        await emit("correction_patch_chat_done", done_payload, durability="commit")
        return CorrectionPatchGenerationResult(
            raw_output="",
            failure_response={
                **done_payload,
                "raw_output": "",
                "operations": [],
                "results": [],
            },
        )
    except Exception as exc:
        for record_item in logger.records:
            await emit("model_call_log", record_item)
        detail = model_call_error_detail(provider, exc)
        error_payload = {
            "job_id": job_id,
            "agent_id": "patchOperationClerk",
            "error": detail,
            "summary": f"Correction patch model call failed: {detail}",
        }
        await emit("correction_patch_model_call_error", error_payload)
        done_payload = {
            "job_id": job_id,
            "accepted_count": 0,
            "changed_count": 0,
            "rejected_count": 1,
            "deferred_count": 0,
            "error": detail,
            "summary": f"Correction patch chat failed: {detail}",
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
        return CorrectionPatchGenerationResult(
            raw_output="",
            failure_response={
                **done_payload,
                "raw_output": "",
                "operations": [],
                "results": [],
            },
        )
    model_call_records = logger.records or ([log_record] if log_record else [])
    for record_item in model_call_records:
        await emit("model_call_log", record_item)
    raw_output = completion.text
    await emit(
        "correction_patch_generation_done",
        {
            "job_id": job_id,
            "agent_id": "patchOperationClerk",
            "raw_output": raw_output,
            "summary": "Correction patch model call completed.",
        },
    )
    await run_thread_to_completion(
        append_session_chat_message,
        session_id,
        "assistant",
        raw_output,
        kind="correction_model_output",
        sessions_dir=sessions_dir,
    )
    return CorrectionPatchGenerationResult(raw_output=raw_output)
