from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from core.model_call_completion import complete_with_logging
from core.json_parsing import parse_json_object_output
from core.model_client import ChatMessage
from harnesses.structured_patch.coverage_direct_judge import run_direct_microop_judge_phase
from harnesses.structured_patch.coverage_phase_payloads import (
    coverage_checkpoint_payload,
    coverage_critic_delta_payload,
    coverage_critic_done_payload,
    coverage_critic_failure_history_record,
    coverage_critic_failure_result_payload,
    coverage_critic_prompt_payload,
    coverage_critic_result_payload,
    coverage_critic_start_payload,
    coverage_critic_success_history_record,
    coverage_decision_patches_payload,
    fallback_modeling_plan_json,
)
from harnesses.structured_patch.coverage_phase_types import (
    CoverageCriticPhaseResult,
    RunnerCoveragePhaseInput,
)
from harnesses.structured_patch.coverage_plan_parsing import parse_plan_coverage_payload
from harnesses.structured_patch.decision_identifier_context import propose_identifier_context_decision_patches
from harnesses.structured_patch.decision_merge import merge_decision_patches
from harnesses.structured_patch.coverage_prompts import (
    PLAN_COVERAGE_CRITIC_SYSTEM_PROMPT,
    build_plan_coverage_critic_user_prompt,
    identifier_policy_text,
)
from core.schemas import StructuredOutputError
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal
from harnesses.structured_patch.runner_operation_state import AsyncOpPatchOperationState


async def run_coverage_critic_phase(
    context: HarnessRunContext,
    phase_input: RunnerCoveragePhaseInput,
    journal: RunJournal,
    operation_state: AsyncOpPatchOperationState,
) -> CoverageCriticPhaseResult:
    initial_phase = phase_input.initial_phase
    specification = context.specification
    structured_model = initial_phase.structured_model
    client = context.client
    logger = context.logger
    coverage_critic_user_template = context.config.prompt_profile.coverage_critic_user_template
    infer_implicit_identifiers = context.config.infer_implicit_identifiers
    direct_microop_judge = context.config.direct_microop_judge
    draft_model_issues = initial_phase.draft_model_issues
    draft_issue_decision_patches = initial_phase.draft_issue_decision_patches
    draft_issue_hard_findings = initial_phase.draft_issue_hard_findings
    decision_patches = phase_input.decision_patches
    emit = context.events.emit
    checkpoint = context.events.checkpoint
    input_prompts = journal.input_prompts
    operation_history = journal.operation_history
    usage_steps = journal.usage_steps
    rejected_operations = operation_state.rejected_operations
    transport_retries = context.config.model_calls.transport_retries
    name_policy = context.config.name_policy
    modeling_plan_json = fallback_modeling_plan_json()
    structured_model_json = json.dumps(structured_model.model_dump(mode="json"), ensure_ascii=False, indent=2)
    pending_decisions_json = json.dumps({"decision_patches": decision_patches}, ensure_ascii=False, indent=2)
    findings: list[dict[str, str]] = list(draft_issue_hard_findings)
    completion_model: str | None = None

    if direct_microop_judge:
        return await run_direct_microop_judge_phase(
            context,
            phase_input,
            journal,
        )

    critic_user_prompt = build_plan_coverage_critic_user_prompt(
        specification=specification,
        modeling_plan_json=modeling_plan_json,
        structured_model_json=structured_model_json,
        identifier_policy=identifier_policy_text(infer_implicit_identifiers=infer_implicit_identifiers),
        pending_decisions_json=pending_decisions_json,
        template=coverage_critic_user_template,
    )
    critic_messages: list[ChatMessage] = [{"role": "user", "content": critic_user_prompt}]
    critic_prompt_payload = coverage_critic_prompt_payload(critic_messages=critic_messages)
    input_prompts.append(critic_prompt_payload)
    await emit("input_prompt", critic_prompt_payload)
    await emit("plan_coverage_critic_start", coverage_critic_start_payload())

    async def on_critic_token(delta: str) -> None:
        await emit("plan_coverage_critic_delta", coverage_critic_delta_payload(delta=delta))

    try:
        critic_completion, critic_log_record = await complete_with_logging(
            client=client,
            logger=logger,
            kind="async_op_patch_coverage_critic",
            system_prompt=PLAN_COVERAGE_CRITIC_SYSTEM_PROMPT,
            user_content=critic_user_prompt,
            messages=critic_messages,
            on_token=on_critic_token,
            transport_retries=transport_retries,
            metadata={"harness": "async-op-patch-model", "stage": "coverage_critic"},
        )
        completion_model = critic_completion.model
        usage_steps.append(critic_completion.usage)
        if critic_log_record is not None:
            await emit("model_call_log", critic_log_record)
        await emit(
            "plan_coverage_critic_done",
            coverage_critic_done_payload(raw_output=critic_completion.text),
        )
        critic_payload = parse_json_object_output(critic_completion.text, label="Plan coverage critic")
        parsed_critic_payload = parse_plan_coverage_payload(critic_payload)
        critic_findings = parsed_critic_payload["findings"]
        findings = [*draft_issue_hard_findings, *critic_findings]
        if infer_implicit_identifiers:
            decision_patches = merge_decision_patches(
                draft_issue_decision_patches,
                parsed_critic_payload["decision_patches"],
                propose_identifier_context_decision_patches(
                    structured_model,
                    name_policy=name_policy,
                ),
                name_policy=name_policy,
            )
        else:
            decision_patches = merge_decision_patches(
                draft_issue_decision_patches,
                parsed_critic_payload["decision_patches"],
                name_policy=name_policy,
            )
        operation_history.append(coverage_critic_success_history_record(critic_finding_count=len(critic_findings)))
        await emit(
            "plan_coverage_critic_result",
            coverage_critic_result_payload(
                findings=findings,
                critic_findings=critic_findings,
                draft_issue_hard_findings=draft_issue_hard_findings,
            ),
        )
        if decision_patches:
            await emit(
                "decision_patches",
                coverage_decision_patches_payload(decision_patches=decision_patches),
            )
        await checkpoint(
            "async-op-patch-after-coverage-critic",
            coverage_checkpoint_payload(
                structured_model=structured_model,
                draft_model_issues=draft_model_issues,
                draft_issue_decision_patches=draft_issue_decision_patches,
                draft_issue_hard_findings=draft_issue_hard_findings,
                findings=findings,
                decision_patches=decision_patches,
            ),
            "Async Operation Patch coverage-critic checkpoint written.",
        )
    except (StructuredOutputError, ValidationError, ValueError) as exc:
        error = str(exc)
        rejected_operations.append({"op": "COVERAGE_CRITIC", "reason": error})
        operation_history.append(coverage_critic_failure_history_record(error=error))
        await emit(
            "plan_coverage_critic_result",
            coverage_critic_failure_result_payload(error=error),
        )

    return CoverageCriticPhaseResult(
        findings=findings,
        decision_patches=decision_patches,
        completion_model=completion_model,
    )


__all__ = ["CoverageCriticPhaseResult", "run_coverage_critic_phase"]
