from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from core.model_call_completion import complete_with_logging
from core.model_call_logger import ModelCallLogger
from core.model_client import ChatMessage, TextModelClient
from harnesses.structured_patch.language_repair import (
    STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT,
    apply_structured_language_renames,
    build_structured_language_repair_user_prompt,
    filter_structured_language_renames,
    parse_structured_language_repair_output,
)
from harnesses.structured_patch.language_repair_pass_payloads import (
    structured_language_repair_delta_payload,
    structured_language_repair_done_payload,
    structured_language_repair_failure_event_payload,
    structured_language_repair_failure_history_record,
    structured_language_repair_prompt_payload,
    structured_language_repair_start_payload,
    structured_language_repair_success_event_payload,
    structured_language_repair_success_history_record,
)
from core.schemas import StructuredModel, StructuredOutputError


async def run_structured_language_repair_pass(
    *,
    specification: str,
    structured_model: StructuredModel,
    client: TextModelClient,
    logger: ModelCallLogger,
    harness: str,
    stage: str,
    title: str,
    prompt_summary: str,
    start_summary: str,
    iteration: int,
    emit: Any,
    input_prompts: list[dict[str, Any]] | None = None,
    operation_history: list[dict[str, Any]] | None = None,
    usage_steps: list[dict[str, Any] | None] | None = None,
    transport_retries: int | None = None,
    emit_model_call_log: bool = True,
) -> tuple[StructuredModel, dict[str, Any]]:
    repair_user_prompt = build_structured_language_repair_user_prompt(
        specification=specification,
        structured_model_json=json.dumps(structured_model.model_dump(mode="json"), ensure_ascii=False, indent=2),
    )
    repair_messages: list[ChatMessage] = [{"role": "user", "content": repair_user_prompt}]
    repair_prompt_payload = structured_language_repair_prompt_payload(
        title=title,
        prompt_summary=prompt_summary,
        system_prompt=STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT,
        repair_messages=repair_messages,
    )
    if input_prompts is not None:
        input_prompts.append(repair_prompt_payload)
    await emit("input_prompt", repair_prompt_payload)
    await emit(
        "structured_language_repair_start",
        structured_language_repair_start_payload(
            iteration=iteration,
            stage=stage,
            start_summary=start_summary,
        ),
    )

    async def on_repair_token(delta: str) -> None:
        await emit(
            "structured_language_repair_delta",
            structured_language_repair_delta_payload(stage=stage, delta=delta),
        )

    try:
        repair_completion, repair_log_record = await complete_with_logging(
            client=client,
            logger=logger,
            kind="structured_language_repair",
            system_prompt=STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT,
            user_content=repair_user_prompt,
            messages=repair_messages,
            on_token=on_repair_token,
            transport_retries=transport_retries,
            metadata={"harness": harness, "stage": stage},
        )
        if usage_steps is not None:
            usage_steps.append(repair_completion.usage)
        if repair_log_record is not None and emit_model_call_log:
            await emit("model_call_log", repair_log_record)
        await emit(
            "structured_language_repair_done",
            structured_language_repair_done_payload(stage=stage, raw_output=repair_completion.text),
        )
        renames = parse_structured_language_repair_output(repair_completion.text)
        accepted_renames, rejected_renames = filter_structured_language_renames(
            specification=specification,
            model=structured_model,
            renames=renames,
        )
        repaired_model, applied_renames = apply_structured_language_renames(structured_model, accepted_renames)
        applied_count = sum(1 for item in applied_renames if item.get("applied"))
        history_item = structured_language_repair_success_history_record(
            iteration=iteration,
            stage=stage,
            renames=renames,
            accepted_renames=accepted_renames,
            rejected_renames=rejected_renames,
            applied_count=applied_count,
        )
        if operation_history is not None:
            operation_history.append(history_item)
        event_payload = structured_language_repair_success_event_payload(
            stage=stage,
            completion_model=repair_completion.model,
            applied_count=applied_count,
            renames=renames,
            accepted_renames=accepted_renames,
            rejected_renames=rejected_renames,
            applied_renames=applied_renames,
        )
        await emit("structured_language_repair_applied", event_payload)
        return repaired_model, event_payload
    except (StructuredOutputError, ValidationError, ValueError) as exc:
        error = str(exc)
        history_item = structured_language_repair_failure_history_record(
            iteration=iteration,
            stage=stage,
            error=error,
        )
        if operation_history is not None:
            operation_history.append(history_item)
        event_payload = structured_language_repair_failure_event_payload(stage=stage, error=error)
        await emit("structured_language_repair_applied", event_payload)
        return structured_model, event_payload


__all__ = ["run_structured_language_repair_pass"]
