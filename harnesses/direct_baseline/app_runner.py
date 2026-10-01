from __future__ import annotations

from pathlib import Path
from typing import Any

from core.model_call_completion import complete_with_logging
from core.model_call_logger import ModelCallLogger
from core.model_client import TextModelClient
from core.operation_loop_result import OperationLoopResult
from core.plantuml_structured import render_structured_model_to_plantuml
from core.providers.factory import provider_descriptor
from harnesses.direct_baseline.prompt_profiles import build_direct_user_prompt, direct_prompt_profile
from harnesses.contracts import HarnessDomainEvent
from harnesses.structured_patch.checkpoints import write_one_shot_run_checkpoint
from harnesses.structured_patch.draft_phase_payloads import (
    draft_model_success_history_record,
    draft_model_validation_failure_payload,
    draft_model_validation_success_payload,
)
from harnesses.structured_patch.model_conversion import structured_model_to_working_model
from harnesses.structured_patch.model_parsing import parse_structured_model_output


async def run_direct_baseline_app_harness(
    *,
    specification: str,
    client: TextModelClient,
    job_id: str,
    model_call_log_dir: Path | None,
    prompt_profile_id: str = "schema_only_v1",
    max_attempts: int = 1,
    on_event: Any | None = None,
) -> OperationLoopResult:
    async def emit(event: str, payload: dict[str, Any]) -> None:
        event_type, detached_payload = HarnessDomainEvent.from_parts(event, payload).detached_parts()
        if on_event is not None:
            await on_event(event_type, detached_payload)

    prompt_profile = direct_prompt_profile(prompt_profile_id)
    user_content = build_direct_user_prompt(specification=specification, prompt_profile=prompt_profile)
    messages = [{"role": "user", "content": user_content}]
    input_prompt = {
        "agent_id": "directBaseline",
        "title": "Direct baseline prompt",
        "summary": "Specification resolved into one direct JSON model prompt.",
        "system_prompt": prompt_profile.system_prompt,
        "messages": messages,
        "prompt_profile": prompt_profile.id,
        "max_attempts": max_attempts,
    }
    await emit("input_prompt", input_prompt)

    logger = ModelCallLogger(job_id=job_id, log_dir=model_call_log_dir)
    raw_output = ""
    last_error = ""
    completion_model = str(getattr(client, "model", "unknown-model"))
    provider_id = str(getattr(client, "provider_id", getattr(client, "provider", "gemini")) or "gemini")
    supports_streaming = provider_descriptor(provider_id).supports_streaming
    usage_steps: list[dict[str, Any] | None] = []
    operation_history: list[dict[str, Any]] = []
    max_attempts = max(1, int(max_attempts or 1))

    for attempt in range(1, max_attempts + 1):
        await emit(
            "direct_baseline_generation_start",
            {
                "agent_id": "directBaseline",
                "iteration": 1,
                "batch_attempt": attempt,
                "max_attempts": max_attempts,
                "summary": f"Generating direct baseline model, attempt {attempt} of {max_attempts}.",
            },
        )

        async def on_token(delta: str) -> None:
            await emit(
                "direct_baseline_generation_delta",
                {
                    "agent_id": "directBaseline",
                    "batch_attempt": attempt,
                    "delta": delta,
                },
            )

        try:
            completion, log_record = await complete_with_logging(
                client=client,
                logger=logger,
                kind="direct_schema_baseline",
                system_prompt=prompt_profile.system_prompt,
                user_content=user_content,
                messages=messages,
                on_token=on_token if supports_streaming else None,
                metadata={"prompt_profile": prompt_profile.id, "attempt": attempt},
            )
            if log_record is not None:
                await emit("model_call_log", log_record)
            raw_output = completion.text
            if not supports_streaming and raw_output:
                await emit(
                    "direct_baseline_generation_delta",
                    {
                        "agent_id": "directBaseline",
                        "batch_attempt": attempt,
                        "delta": raw_output,
                    },
                )
            completion_model = completion.model or completion_model
            usage_steps.append(completion.usage)
            await emit(
                "direct_baseline_generation_done",
                {
                    "agent_id": "directBaseline",
                    "batch_attempt": attempt,
                    "raw_output": raw_output,
                    "summary": f"Direct baseline output received for attempt {attempt}.",
                },
            )
            structured_model = parse_structured_model_output(raw_output, repair_missing_endpoint_entities=True)
        except Exception as exc:
            last_error = str(exc) or repr(exc)
            operation_history.append(
                {
                    "iteration": 1,
                    "batch_attempt": attempt,
                    "accepted": [],
                    "rejected": [{"op": "DIRECT_STRUCTURED_MODEL", "error": last_error, "actual_raw_output": raw_output}],
                    "focus": "Produce one direct structured conceptual model.",
                    "feedback": last_error,
                }
            )
            failure_payload = draft_model_validation_failure_payload(attempt=attempt, error=last_error, max_attempts=max_attempts)
            await emit(
                "direct_baseline_validation",
                {
                    **failure_payload,
                    "agent_id": "directBaseline",
                    "summary": failure_payload.get("summary") or "Direct baseline model failed validation.",
                },
            )
            if attempt >= max_attempts:
                raise
            continue

        working_model = structured_model_to_working_model(structured_model)
        plantuml = render_structured_model_to_plantuml(structured_model)
        plantuml_url = ""
        operation_history.append(draft_model_success_history_record(attempt=attempt, structured_model=structured_model))
        success_payload = {
            **draft_model_validation_success_payload(
                attempt=attempt,
                structured_model=structured_model,
                deterministic_repairs=[],
            ),
            "agent_id": "directBaseline",
            "summary": f"{len(structured_model.entities)} entities, {len(structured_model.relationships)} relationships validated.",
        }
        await emit(
            "direct_baseline_validation",
            success_payload,
        )
        await emit(
            "structured_model_validated",
            success_payload,
        )
        await emit("working_model", {"working_model": working_model.model_dump(mode="json"), "model": working_model.model_dump(mode="json")})
        await emit("plantuml_preview", {"plantuml": plantuml, "plantuml_url": plantuml_url})
        checkpoint_record = write_one_shot_run_checkpoint(
            model_call_log_dir,
            job_id=job_id,
            stage="direct_baseline_final",
            payload={"structured_model": structured_model.model_dump(mode="json"), "prompt_profile": prompt_profile.id},
        )
        if checkpoint_record is not None:
            await emit(
                "checkpoint_written",
                {
                    "agent_id": "directBaseline",
                    **checkpoint_record,
                    "summary": "Direct baseline model checkpoint written.",
                },
            )
        return OperationLoopResult(
            job_id=job_id,
            working_model=working_model,
            structured_model=structured_model,
            plantuml=plantuml,
            plantuml_url=plantuml_url,
            operation_history=operation_history,
            input_prompts=[input_prompt],
            completion_checks=[],
            plan_updates=[],
            model_call_log_dir=str(model_call_log_dir) if model_call_log_dir is not None else None,
            model_call_logs=logger.records,
            iterations=1,
            accepted_operation_count=1,
            rejected_operation_count=sum(len(item.get("rejected") or []) for item in operation_history),
            stop_reason="direct_baseline_complete",
            model=completion_model,
            usage_steps=usage_steps,
        )

    raise RuntimeError(last_error or "Direct baseline generation failed.")


__all__ = ["run_direct_baseline_app_harness"]
