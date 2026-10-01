from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.model_call_completion import complete_with_logging
from core.model_call_logger import ModelCallLogger
from core.providers.factory import provider_descriptor
from backend.persistence.session_chat import append_session_chat_message
from backend.services.async_file_work import run_thread_to_completion
from backend.services.correction_clients import model_call_error_detail
from backend.services.correction_prompts import MODEL_QUESTION_SYSTEM_PROMPT
from backend.services.trace_event_recorder import TraceEventRecorder


@dataclass(slots=True)
class ModelQuestionGenerationResult:
    raw_output: str
    answer: str
    failure_response: dict[str, Any] | None = None


async def generate_model_question_answer(
    *,
    job_id: str,
    provider: str,
    client: Any,
    logger: ModelCallLogger,
    event_recorder: TraceEventRecorder,
    emit: Any,
    session_id: str | None,
    sessions_dir: Path,
    user_prompt: str,
    messages: list[dict[str, str]],
) -> ModelQuestionGenerationResult:
    await emit(
        "question_generation_start",
        {
            "job_id": job_id,
            "agent_id": "modelQuestionAnswerer",
            "summary": "Streaming read-only question answer.",
        },
    )

    async def on_question_token(delta: str) -> None:
        if not delta:
            return
        await event_recorder.emit_delta(
            "question_generation_delta",
            {
                "job_id": job_id,
                "agent_id": "modelQuestionAnswerer",
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
            kind="run_question_answer",
            system_prompt=MODEL_QUESTION_SYSTEM_PROMPT,
            user_content=user_prompt,
            messages=messages,
            on_token=on_question_token if supports_streaming else None,
            metadata={"source": "run_question_chat"},
        )
        if not supports_streaming and completion.text:
            await on_question_token(completion.text)
    except asyncio.CancelledError:
        for record_item in logger.records:
            await emit("model_call_log", record_item)
        detail = "Question answer generation was interrupted before it completed."
        await emit(
            "question_model_call_error",
            {
                "job_id": job_id,
                "agent_id": "modelQuestionAnswerer",
                "error": detail,
                "summary": detail,
            },
        )
        done_payload = {
            "job_id": job_id,
            "answer": "",
            "error": detail,
            "interrupted": True,
            "summary": detail,
        }
        await run_thread_to_completion(
            append_session_chat_message,
            session_id,
            "assistant",
            detail,
            kind="question",
            sessions_dir=sessions_dir,
        )
        await emit("question_chat_done", done_payload, durability="commit")
        return ModelQuestionGenerationResult(
            raw_output="",
            answer="",
            failure_response={**done_payload, "raw_output": ""},
        )
    except Exception as exc:
        for record_item in logger.records:
            await emit("model_call_log", record_item)
        detail = model_call_error_detail(provider, exc)
        await emit(
            "question_model_call_error",
            {
                "job_id": job_id,
                "agent_id": "modelQuestionAnswerer",
                "error": detail,
                "summary": f"Question model call failed: {detail}",
            },
        )
        done_payload = {
            "job_id": job_id,
            "answer": "",
            "error": detail,
            "summary": f"Question failed: {detail}",
        }
        await run_thread_to_completion(
            append_session_chat_message,
            session_id,
            "assistant",
            done_payload["summary"],
            kind="question",
            sessions_dir=sessions_dir,
        )
        await emit("question_chat_done", done_payload, durability="commit")
        return ModelQuestionGenerationResult(
            raw_output="",
            answer="",
            failure_response={**done_payload, "raw_output": ""},
        )

    model_call_records = logger.records or ([log_record] if log_record else [])
    for record_item in model_call_records:
        await emit("model_call_log", record_item)
    raw_output = completion.text
    answer = raw_output.strip()
    await emit(
        "question_generation_done",
        {
            "job_id": job_id,
            "agent_id": "modelQuestionAnswerer",
            "raw_output": raw_output,
            "answer": answer,
            "summary": "Question model call completed.",
        },
    )
    return ModelQuestionGenerationResult(raw_output=raw_output, answer=answer)


__all__ = ["ModelQuestionGenerationResult", "generate_model_question_answer"]
