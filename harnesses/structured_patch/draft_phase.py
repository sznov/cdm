from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from core.model_call_completion import complete_with_logging
from core.model_client import ChatMessage
from harnesses.structured_patch.model_issue_decisions import decision_patches_from_structured_model_issues
from harnesses.structured_patch.model_issue_findings import findings_from_structured_model_issues
from harnesses.structured_patch.model_parsing import parse_structured_model_packet_output_with_repairs
from harnesses.structured_patch.draft_phase_payloads import (
    draft_generation_delta_payload,
    draft_generation_done_payload,
    draft_generation_start_payload,
    draft_model_checkpoint_payload,
    draft_model_failure_history_record,
    draft_model_issues_payload,
    draft_model_retry_feedback_payload,
    draft_model_success_history_record,
    draft_model_validation_failure_payload,
    draft_model_validation_success_payload,
    draft_prompt_input_payload,
)
from harnesses.structured_patch.draft_prompts import (
    SIMPLE_DRAFT_SYSTEM_PROMPT,
    build_simple_draft_user_prompt,
    format_draft_model_retry_feedback,
)
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal
from core.schemas import StructuredModel, StructuredOutputError


@dataclass
class DraftModelPhaseResult:
    structured_model: StructuredModel | None
    draft_model_issues: list[dict[str, Any]]
    draft_issue_decision_patches: list[dict[str, Any]]
    draft_issue_hard_findings: list[dict[str, str]]
    completion_model: str | None = None


async def run_draft_model_phase(
    context: HarnessRunContext,
    journal: RunJournal,
) -> DraftModelPhaseResult:
    specification = context.specification
    client = context.client
    logger = context.logger
    max_attempts = context.config.model_calls.max_attempts
    transport_retries = context.config.model_calls.transport_retries
    draft_user_template = context.config.prompt_profile.draft_user_template
    emit = context.events.emit
    checkpoint = context.events.checkpoint
    input_prompts = journal.input_prompts
    operation_history = journal.operation_history
    usage_steps = journal.usage_steps
    name_policy = context.config.name_policy
    structured_model: StructuredModel | None = None
    draft_model_issues: list[dict[str, Any]] = []
    draft_issue_decision_patches: list[dict[str, Any]] = []
    draft_issue_hard_findings: list[dict[str, str]] = []
    completion_model: str | None = None

    draft_user_prompt = build_simple_draft_user_prompt(
        specification=specification,
        template=draft_user_template,
    )
    draft_messages: list[ChatMessage] = [{"role": "user", "content": draft_user_prompt}]
    draft_prompt_payload = draft_prompt_input_payload(draft_messages=draft_messages, max_attempts=max_attempts)
    input_prompts.append(draft_prompt_payload)
    await emit("input_prompt", draft_prompt_payload)

    for attempt in range(1, max_attempts + 1):
        await emit(
            "draft_model_generation_start",
            draft_generation_start_payload(attempt=attempt, max_attempts=max_attempts),
        )

        async def on_draft_token(delta: str, *, current_attempt: int = attempt) -> None:
            await emit(
                "draft_model_generation_delta",
                draft_generation_delta_payload(attempt=current_attempt, delta=delta),
            )

        completion, log_record = await complete_with_logging(
            client=client,
            logger=logger,
            kind="async_op_patch_draft_model",
            system_prompt=SIMPLE_DRAFT_SYSTEM_PROMPT,
            user_content=draft_messages[-1]["content"],
            messages=draft_messages,
            on_token=on_draft_token,
            transport_retries=transport_retries,
            metadata={"harness": "async-op-patch-model", "stage": "draft_model", "attempt": attempt},
        )
        completion_model = completion.model
        usage_steps.append(completion.usage)
        if log_record is not None:
            await emit("model_call_log", log_record)
        await emit(
            "draft_model_generation_done",
            draft_generation_done_payload(attempt=attempt, raw_output=completion.text),
        )

        try:
            structured_model, draft_model_issues, deterministic_repairs = parse_structured_model_packet_output_with_repairs(
                completion.text,
                name_policy=name_policy,
            )
            draft_issue_decision_patches = decision_patches_from_structured_model_issues(
                draft_model_issues,
                name_policy=name_policy,
            )
            draft_issue_hard_findings = findings_from_structured_model_issues(draft_model_issues)
            await emit(
                "draft_model_validation",
                draft_model_validation_success_payload(
                    attempt=attempt,
                    structured_model=structured_model,
                    deterministic_repairs=deterministic_repairs,
                ),
            )
            if draft_model_issues:
                await emit(
                    "draft_model_issues",
                    draft_model_issues_payload(
                        draft_model_issues=draft_model_issues,
                        draft_issue_decision_patches=draft_issue_decision_patches,
                        draft_issue_hard_findings=draft_issue_hard_findings,
                    ),
                )
            operation_history.append(
                draft_model_success_history_record(attempt=attempt, structured_model=structured_model)
            )
            await checkpoint(
                "async-op-patch-after-draft",
                draft_model_checkpoint_payload(
                    structured_model=structured_model,
                    draft_model_issues=draft_model_issues,
                    draft_issue_decision_patches=draft_issue_decision_patches,
                    draft_issue_hard_findings=draft_issue_hard_findings,
                ),
                "Async Operation Patch draft model checkpoint written.",
            )
            break
        except (StructuredOutputError, ValidationError) as exc:
            error = str(exc)
            operation_history.append(
                draft_model_failure_history_record(attempt=attempt, error=error, raw_output=completion.text)
            )
            await emit(
                "draft_model_validation",
                draft_model_validation_failure_payload(attempt=attempt, error=error, max_attempts=max_attempts),
            )
            if attempt >= max_attempts:
                break
            feedback = format_draft_model_retry_feedback(error=error, raw_output=completion.text)
            draft_messages.append({"role": "assistant", "content": completion.text})
            draft_messages.append({"role": "user", "content": feedback})
            await emit(
                "draft_model_retry_feedback",
                draft_model_retry_feedback_payload(attempt=attempt, feedback=feedback),
            )

    return DraftModelPhaseResult(
        structured_model=structured_model,
        draft_model_issues=draft_model_issues,
        draft_issue_decision_patches=draft_issue_decision_patches,
        draft_issue_hard_findings=draft_issue_hard_findings,
        completion_model=completion_model,
    )


__all__ = ["DraftModelPhaseResult", "run_draft_model_phase"]
