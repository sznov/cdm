from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.model_call_logger import ModelCallLogger
from backend.api.models import QuestionRequest
from backend.persistence.session_chat import append_session_chat_message, session_comments_context
from backend.services.async_file_work import run_thread_to_completion
from backend.services.active_run_registry import ActiveRun, run_is_active
from backend.services.correction_prompts import MODEL_QUESTION_SYSTEM_PROMPT, build_model_question_user_prompt
from backend.services.question_generation import generate_model_question_answer
from backend.services.question_context import load_model_question_context
from backend.services.post_run_stream_control import PostRunStreamControl
from backend.services.runtime_config import provider_label
from backend.services.run_operation_claims import claim_recorded_run_operation
from backend.services.run_operation_registry import (
    RunOperationHandle,
    RunOperationKind,
    RunOperationRegistry,
)
from backend.services.trace_event_recorder import AsyncEventSink


async def _ask_model_question_core(
    job_id: str,
    request: QuestionRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    event_sink: AsyncEventSink | None = None,
    stream_control: PostRunStreamControl | None = None,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_handle: RunOperationHandle,
) -> dict[str, Any]:
    if not await operation_handle.begin_provider_phase():
        raise asyncio.CancelledError
    context = load_model_question_context(
        job_id,
        request,
        runs_dir=runs_dir,
        sessions_dir=sessions_dir,
        event_sink=event_sink,
        stream_control=stream_control,
        active_runs=active_runs,
    )
    run_dir = context.run_dir
    record = context.record
    specification = context.specification
    structured_model = context.structured_model
    working_model_payload = context.working_model_payload
    question = context.question
    provider = context.provider
    model_name = context.model_name
    base_url = context.base_url
    client = context.client
    session_id = context.session_id
    decision_patches = context.decision_patches
    event_recorder = context.event_recorder
    emit = context.emit
    response: dict[str, Any] | None = None
    try:
        await run_thread_to_completion(
            append_session_chat_message,
            session_id,
            "user",
            question,
            kind="question",
            sessions_dir=context.sessions_dir,
        )
        await emit(
            "question_chat_start",
            {
                "job_id": job_id,
                "agent_id": "modelQuestionAnswerer",
                "provider": provider_label(provider),
                "model": model_name,
                "base_url": base_url,
                "question": question,
                "summary": "Read-only model question submitted.",
            },
        )

        user_prompt = build_model_question_user_prompt(
            question=question,
            specification=specification,
            structured_model=structured_model,
            working_model_payload=working_model_payload,
            decision_patches=decision_patches,
        )
        session_context = await asyncio.to_thread(
            session_comments_context,
            session_id,
            sessions_dir=context.sessions_dir,
        )
        if session_context:
            user_prompt += f"\n\nSESSION CONTEXT FROM USER COMMENTS AND CHAT:\n{session_context}\n"
        messages = [{"role": "user", "content": user_prompt}]
        await emit(
            "input_prompt",
            {
                "agent_id": "modelQuestionAnswerer",
                "title": "Model question prompt",
                "summary": "Question resolved against the run's saved specification, current model, and surfaced decisions.",
                "system_prompt": MODEL_QUESTION_SYSTEM_PROMPT,
                "messages": messages,
            },
        )

        model_call_dir = run_dir / "model_calls"
        logger = ModelCallLogger(job_id=job_id, log_dir=model_call_dir)
        generation_result = await generate_model_question_answer(
            job_id=job_id,
            provider=provider,
            client=client,
            logger=logger,
            event_recorder=event_recorder,
            emit=emit,
            session_id=session_id,
            sessions_dir=context.sessions_dir,
            user_prompt=user_prompt,
            messages=messages,
        )
        if generation_result.failure_response is not None:
            await operation_handle.begin_finalizing(
                cancellation_handled=bool(
                    generation_result.failure_response.get("interrupted")
                )
            )
            response = generation_result.failure_response
        else:
            if not await operation_handle.begin_draining():
                raise asyncio.CancelledError
            raw_output = generation_result.raw_output
            answer = generation_result.answer
            done_payload = {
                "job_id": job_id,
                "answer": answer,
                "summary": "Question answered.",
            }
            await operation_handle.begin_finalizing()
            await run_thread_to_completion(
                append_session_chat_message,
                session_id,
                "assistant",
                answer,
                kind="question",
                sessions_dir=context.sessions_dir,
            )
            await emit("question_chat_done", done_payload, durability="commit")
            response = {
                **done_payload,
                "raw_output": raw_output,
            }
    except asyncio.CancelledError:
        await event_recorder.emit(
            "question_interrupted",
            {
                "job_id": job_id,
                "interrupted": True,
                "summary": "Question operation was interrupted before commit.",
            },
            durability="commit",
        )
        raise
    finally:
        await event_recorder.close()
    if response is None:  # pragma: no cover - all completed paths assign a response
        raise RuntimeError("Question operation completed without a response.")
    return {**response, **event_recorder.sequence_summary()}


async def ask_model_question_core(
    job_id: str,
    request: QuestionRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    event_sink: AsyncEventSink | None = None,
    stream_control: PostRunStreamControl | None = None,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_registry: RunOperationRegistry,
) -> dict[str, Any]:
    if run_is_active(job_id, active_runs):
        raise HTTPException(
            status_code=409,
            detail="Cannot ask about a run while it is still active.",
        )
    async with claim_recorded_run_operation(
        job_id,
        RunOperationKind.QUESTION,
        runs_dir=runs_dir,
        registry=operation_registry,
    ) as operation_handle:
        if stream_control is not None:
            await stream_control.bind(operation_handle)
        return await _ask_model_question_core(
            job_id,
            request,
            runs_dir=runs_dir,
            sessions_dir=sessions_dir,
            event_sink=event_sink,
            stream_control=stream_control,
            active_runs=active_runs,
            operation_handle=operation_handle,
        )


__all__ = ["ask_model_question_core"]
