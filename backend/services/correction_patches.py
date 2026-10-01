from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.model_call_logger import ModelCallLogger
from backend.api.models import CorrectionPatchRequest
from backend.api.settings import RUN_TRACE_FILENAME
from backend.persistence.session_chat import append_session_chat_message
from backend.persistence.run_paths import safe_run_dir
from harnesses.structured_patch.patch_prompts import (
    PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
)
from core.schemas import StructuredOutputError
from backend.services.active_run_registry import ActiveRun, run_is_active
from backend.services.correction_patch_completion import complete_correction_patch_application
from backend.services.correction_patch_context import load_freeform_correction_context
from backend.services.correction_patch_generation import generate_correction_patch_output
from backend.services.correction_patch_application import apply_correction_patch_operations
from backend.services.correction_patch_parsing import (
    correction_patch_parse_error_response,
    parse_correction_patch_operations,
)
from backend.services.correction_patch_prompting import build_freeform_correction_patch_prompt
from backend.services.runtime_config import provider_label
from backend.services.run_operation_claims import claim_recorded_run_operation
from backend.services.run_operation_registry import (
    RunOperationHandle,
    RunOperationKind,
    RunOperationRegistry,
)
from backend.services.post_run_stream_control import PostRunStreamControl
from backend.services.async_file_work import run_thread_to_completion
from backend.services.correction_events import (
    CorrectionApplicationEventBuffer,
    CorrectionEventRecorder,
)
from backend.services.trace_event_recorder import AsyncEventSink

async def _apply_freeform_correction_core(
    job_id: str,
    request: CorrectionPatchRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    event_sink: AsyncEventSink | None = None,
    stream_control: PostRunStreamControl | None = None,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_handle: RunOperationHandle,
    event_recorder: CorrectionEventRecorder,
) -> dict[str, Any]:
    if not await operation_handle.begin_provider_phase():
        raise asyncio.CancelledError
    context = load_freeform_correction_context(
        job_id,
        request,
        runs_dir=runs_dir,
        sessions_dir=sessions_dir,
        event_sink=event_sink,
        stream_control=stream_control,
        active_runs=active_runs,
        event_recorder=event_recorder,
    )
    run_dir = context.run_dir
    model = context.model
    specification = context.specification
    event_recorder = context.event_recorder
    emit = context.emit
    provider = context.provider
    model_name = context.model_name
    base_url = context.base_url
    client = context.client
    session_id = context.session_id
    message = context.message
    await run_thread_to_completion(
        append_session_chat_message,
        session_id,
        "user",
        message,
        kind="correction",
        sessions_dir=context.sessions_dir,
    )
    started_payload = {
        "job_id": job_id,
        "agent_id": "patchOperationClerk",
        "provider": provider_label(provider),
        "model": model_name,
        "base_url": base_url,
        "user_message": message,
        "summary": "Free-form correction submitted for structured patch generation.",
    }
    await emit("correction_patch_chat_start", started_payload)

    prompt = await asyncio.to_thread(
        build_freeform_correction_patch_prompt,
        request=request,
        message=message,
        specification=specification,
        model=model,
        session_id=session_id,
        sessions_dir=context.sessions_dir,
        prompt_template=context.patch_policy.prompt_template,
    )
    user_prompt = prompt.user_prompt
    messages = prompt.messages
    allowed_ops = prompt.allowed_ops
    await emit(
        "input_prompt",
        {
            "agent_id": "patchOperationClerk",
            "title": "Correction patch prompt",
            "summary": "User correction resolved against the run's saved specification and current model.",
            "system_prompt": PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
            "messages": messages,
        },
    )

    model_call_dir = run_dir / "model_calls"
    logger = ModelCallLogger(job_id=job_id, log_dir=model_call_dir)
    generation_result = await generate_correction_patch_output(
        job_id=job_id,
        request=request,
        provider=provider,
        client=client,
        logger=logger,
        event_recorder=event_recorder,
        emit=emit,
        session_id=session_id,
        sessions_dir=context.sessions_dir,
        user_prompt=user_prompt,
        messages=messages,
        allowed_ops=allowed_ops,
    )
    if generation_result.failure_response is not None:
        await operation_handle.begin_finalizing(
            cancellation_handled=bool(
                generation_result.failure_response.get("interrupted")
            )
        )
        return generation_result.failure_response
    if not await operation_handle.begin_draining():
        raise asyncio.CancelledError
    raw_output = generation_result.raw_output

    try:
        operations = parse_correction_patch_operations(raw_output, max_operations=request.max_operations)
    except StructuredOutputError as exc:
        await operation_handle.begin_finalizing()
        return await correction_patch_parse_error_response(
            job_id=job_id,
            raw_output=raw_output,
            error=exc,
            emit=emit,
            session_id=session_id,
            sessions_dir=context.sessions_dir,
        )

    application_events = CorrectionApplicationEventBuffer()
    application_result = apply_correction_patch_operations(
        job_id=job_id,
        model=model,
        specification=specification,
        operations=operations,
        allowed_ops=allowed_ops,
        emit=application_events.emit,
        operation_guard=context.patch_policy.operation_guard,
        name_policy=context.patch_policy.name_policy,
    )
    await application_events.drain_to(event_recorder)
    return await complete_correction_patch_application(
        job_id=job_id,
        context=context,
        logger=logger,
        raw_output=raw_output,
        operations=operations,
        application_result=application_result,
        operation_handle=operation_handle,
    )


async def apply_freeform_correction_core(
    job_id: str,
    request: CorrectionPatchRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    event_sink: AsyncEventSink | None = None,
    stream_control: PostRunStreamControl | None = None,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_registry: RunOperationRegistry,
    event_recorder: CorrectionEventRecorder | None = None,
) -> dict[str, Any]:
    if run_is_active(job_id, active_runs):
        raise HTTPException(
            status_code=409,
            detail="Cannot apply correction patches while the run is still active.",
        )
    recorder = event_recorder
    owns_recorder = recorder is None
    response: dict[str, Any] | None = None
    async with claim_recorded_run_operation(
        job_id,
        RunOperationKind.CORRECTION,
        runs_dir=runs_dir,
        registry=operation_registry,
    ) as operation_handle:
        if stream_control is not None:
            await stream_control.bind(operation_handle)
        if recorder is None:
            recorder = CorrectionEventRecorder(
                trace_path=(
                    safe_run_dir(job_id, runs_dir=runs_dir)
                    / RUN_TRACE_FILENAME
                ),
                event_sink=event_sink,
                stream_control=stream_control,
            )
        try:
            response = await _apply_freeform_correction_core(
                job_id,
                request,
                runs_dir=runs_dir,
                sessions_dir=sessions_dir,
                event_sink=event_sink,
                stream_control=stream_control,
                active_runs=active_runs,
                operation_handle=operation_handle,
                event_recorder=recorder,
            )
        except asyncio.CancelledError:
            await recorder.emit(
                "correction_operation_interrupted",
                {
                    "job_id": job_id,
                    "interrupted": True,
                    "summary": "Correction operation was interrupted before commit.",
                },
                durability="commit",
            )
            raise
        finally:
            if owns_recorder:
                await recorder.close()
    if recorder is None:  # pragma: no cover - constructed inside ownership
        raise RuntimeError("Correction operation has no event recorder.")
    if response is None:  # pragma: no cover - completed paths return a response
        raise RuntimeError("Correction operation completed without a response.")
    if owns_recorder:
        return {**response, **recorder.sequence_summary()}
    return response


__all__ = ["apply_freeform_correction_core"]
