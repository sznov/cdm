from __future__ import annotations

import asyncio
import json
from typing import Any

from core.model_call_completion import complete_with_logging
from core.model_call_logger import ModelCallLogger
from core.providers.factory import provider_descriptor
from harnesses.structured_patch.language_repair import (
    STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT,
    apply_structured_language_renames,
    build_structured_language_repair_user_prompt,
    filter_structured_language_renames,
    parse_structured_language_repair_output,
)
from core.schemas import StructuredModel
from backend.services.correction_clients import model_call_error_detail
from backend.services.trace_event_recorder import AsyncEventEmitter


async def run_correction_post_patch_language_repair(
    *,
    job_id: str,
    provider: str,
    client: Any,
    logger: ModelCallLogger,
    specification: str,
    model: StructuredModel,
    emit: AsyncEventEmitter,
) -> tuple[StructuredModel, dict[str, Any]]:
    repair_user_prompt = build_structured_language_repair_user_prompt(
        specification=specification,
        structured_model_json=json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2),
    )
    repair_messages = [{"role": "user", "content": repair_user_prompt}]
    await emit(
        "input_prompt",
        {
            "agent_id": "structuredLanguageRepair",
            "title": "Correction post-patch language repair prompt",
            "summary": "Correction-patched model resolved into a name-only language repair prompt.",
            "system_prompt": STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT,
            "messages": repair_messages,
        },
    )
    await emit(
        "structured_language_repair_start",
        {
            "job_id": job_id,
            "agent_id": "structuredLanguageRepair",
            "stage": "correction_post_patch_language_repair",
            "summary": "Checking correction-produced names against the specification language.",
        },
    )

    async def on_language_repair_token(delta: str) -> None:
        if not delta:
            return
        await emit(
            "structured_language_repair_delta",
            {
                "job_id": job_id,
                "agent_id": "structuredLanguageRepair",
                "stage": "correction_post_patch_language_repair",
                "delta": delta,
            },
        )

    try:
        try:
            supports_streaming = provider_descriptor(provider).supports_streaming
        except ValueError:
            supports_streaming = True
        repair_completion, repair_log_record = await complete_with_logging(
            client=client,
            logger=logger,
            kind="structured_language_repair",
            system_prompt=STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT,
            user_content=repair_user_prompt,
            messages=repair_messages,
            on_token=on_language_repair_token if supports_streaming else None,
            metadata={"source": "freeform_correction_chat", "stage": "correction_post_patch_language_repair"},
        )
        if not supports_streaming and repair_completion.text:
            await on_language_repair_token(repair_completion.text)
        repair_call_records = logger.records or ([repair_log_record] if repair_log_record else [])
        for record_item in repair_call_records:
            if record_item.get("kind") == "structured_language_repair":
                await emit("model_call_log", record_item)
        await emit(
            "structured_language_repair_done",
            {
                "job_id": job_id,
                "agent_id": "structuredLanguageRepair",
                "stage": "correction_post_patch_language_repair",
                "raw_output": repair_completion.text,
                "summary": "Structured language repair output received.",
            },
        )
        renames = parse_structured_language_repair_output(repair_completion.text)
        accepted_renames, rejected_renames = filter_structured_language_renames(
            specification=specification,
            model=model,
            renames=renames,
        )
        model, applied_renames = apply_structured_language_renames(model, accepted_renames)
        applied_count = sum(1 for item in applied_renames if item.get("applied"))
        language_repair_record = {
            "applied_count": applied_count,
            "accepted_rename_count": len(accepted_renames),
            "rejected_rename_count": len(rejected_renames),
            "renames": renames,
            "accepted_renames": accepted_renames,
            "rejected_renames": rejected_renames,
            "applied_renames": applied_renames,
        }
        await emit(
            "structured_language_repair_applied",
            {
                "job_id": job_id,
                "agent_id": "structuredLanguageRepair",
                "stage": "correction_post_patch_language_repair",
                **language_repair_record,
                "summary": f"Applied {applied_count} structured rename(s).",
            },
        )
        return model, language_repair_record
    except asyncio.CancelledError:
        for record_item in logger.records:
            if record_item.get("kind") == "structured_language_repair":
                await emit("model_call_log", record_item)
        detail = "Structured language repair was interrupted after correction patch operations were applied."
        language_repair_record = {
            "applied_count": 0,
            "interrupted": True,
            "error": detail,
        }
        await emit(
            "structured_language_repair_applied",
            {
                "job_id": job_id,
                "agent_id": "structuredLanguageRepair",
                "stage": "correction_post_patch_language_repair",
                **language_repair_record,
                "summary": detail,
            },
        )
        return model, language_repair_record
    except Exception as exc:
        for record_item in logger.records:
            if record_item.get("kind") == "structured_language_repair":
                await emit("model_call_log", record_item)
        language_repair_record = {"applied_count": 0, "error": model_call_error_detail(provider, exc)}
        await emit(
            "structured_language_repair_applied",
            {
                "job_id": job_id,
                "agent_id": "structuredLanguageRepair",
                "stage": "correction_post_patch_language_repair",
                **language_repair_record,
                "summary": f"Structured language repair failed: {language_repair_record['error']}",
            },
        )
        return model, language_repair_record


__all__ = ["run_correction_post_patch_language_repair"]
