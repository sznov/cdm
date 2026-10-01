from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.model_call_completion import complete_with_logging
from core.model_client import ChatMessage
from harnesses.structured_patch.patch_parse_stream import (
    StructuredPatchOperationStreamParser,
    parse_structured_patch_operations,
)
from harnesses.structured_patch.patch_generation_phase_payloads import (
    patch_operation_generation_delta_payload,
    patch_operation_generation_done_payload,
    patch_operation_generation_start_payload,
    patch_operation_history_record,
    patch_operation_parse_error_payload,
    patch_operation_prompt_payload,
)
from harnesses.structured_patch.patch_prompts import build_patch_operation_clerk_user_prompt
from harnesses.structured_patch.patch_application_phase import StructuredPatchBatchApplier
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal
from harnesses.structured_patch.runner_initial_phase import InitialStructuredModelPhaseResult
from harnesses.structured_patch.runner_operation_state import AsyncOpPatchOperationState
from core.schemas import StructuredOutputError


@dataclass(frozen=True, slots=True)
class PatchGenerationPhaseInput:
    initial_phase: InitialStructuredModelPhaseResult
    findings: list[dict[str, str]]


async def run_patch_generation_phase(
    context: HarnessRunContext,
    phase_input: PatchGenerationPhaseInput,
    journal: RunJournal,
    operation_state: AsyncOpPatchOperationState,
    patch_applier: StructuredPatchBatchApplier,
) -> str | None:
    specification = context.specification
    structured_model = patch_applier.model
    client = context.client
    logger = context.logger
    findings = phase_input.findings
    decision_patches = patch_applier.decision_patches
    patch_clerk_system_prompt = context.config.prompt_profile.patch_clerk_system_prompt
    patch_clerk_user_template = context.config.prompt_profile.patch_clerk_user_template
    emit = context.events.emit
    checkpoint = context.events.checkpoint
    input_prompts = journal.input_prompts
    operation_history = journal.operation_history
    usage_steps = journal.usage_steps
    transport_retries = context.config.model_calls.transport_retries

    def checkpoint_payload() -> dict[str, Any]:
        initial_phase = phase_input.initial_phase
        return {
            "structured_model": patch_applier.model.model_dump(mode="json"),
            "draft_model_issues": initial_phase.draft_model_issues,
            "draft_issue_decision_patches": initial_phase.draft_issue_decision_patches,
            "draft_issue_hard_findings": initial_phase.draft_issue_hard_findings,
            "findings": findings,
            "decision_patches": patch_applier.decision_patches,
            "applied_operations": operation_state.applied_operations,
            "already_satisfied_operations": operation_state.already_satisfied_operations,
            "rejected_operations": operation_state.rejected_operations,
            "deferred_operations": operation_state.deferred_operations,
        }
    pending_decisions_json = json.dumps({"decision_patches": decision_patches}, ensure_ascii=False, indent=2)
    patch_user_prompt = build_patch_operation_clerk_user_prompt(
        specification=specification,
        coverage_findings_json=json.dumps({"findings": findings}, ensure_ascii=False, indent=2),
        structured_model_json=json.dumps(structured_model.model_dump(mode="json"), ensure_ascii=False, indent=2),
        pending_decisions_json=pending_decisions_json,
        template=patch_clerk_user_template,
    )
    patch_messages: list[ChatMessage] = [{"role": "user", "content": patch_user_prompt}]
    patch_prompt_payload = patch_operation_prompt_payload(
        patch_clerk_system_prompt=patch_clerk_system_prompt,
        patch_messages=patch_messages,
    )
    input_prompts.append(patch_prompt_payload)
    await emit("input_prompt", patch_prompt_payload)
    await emit("patch_operation_generation_start", patch_operation_generation_start_payload())
    stream_parser = StructuredPatchOperationStreamParser()
    stream_parse_errors: list[str] = []

    async def on_patch_token(delta: str) -> None:
        await emit("patch_operation_generation_delta", patch_operation_generation_delta_payload(delta=delta))
        operations, errors = stream_parser.feed(delta)
        for error in errors:
            stream_parse_errors.append(error)
            await emit("structured_patch_operation_parse_error", patch_operation_parse_error_payload(error=error))
        for operation in operations:
            await patch_applier.apply_parsed_operation(operation)

    patch_completion, patch_log_record = await complete_with_logging(
        client=client,
        logger=logger,
        kind="async_op_patch_operations",
        system_prompt=patch_clerk_system_prompt,
        user_content=patch_user_prompt,
        messages=patch_messages,
        on_token=on_patch_token,
        transport_retries=transport_retries,
        metadata={"harness": "async-op-patch-model", "stage": "patch_operations"},
    )
    completion_model = patch_completion.model
    usage_steps.append(patch_completion.usage)
    final_operations, final_errors = stream_parser.feed("", final=True)
    for error in final_errors:
        stream_parse_errors.append(error)
        await emit("structured_patch_operation_parse_error", patch_operation_parse_error_payload(error=error))
    if patch_applier.operation_count() == 0 and not final_operations:
        try:
            final_operations.extend(parse_structured_patch_operations(patch_completion.text))
        except StructuredOutputError as exc:
            stream_parse_errors.append(str(exc))
    for operation in final_operations:
        await patch_applier.apply_parsed_operation(operation)
    await patch_applier.retry_deferred_operations()
    await patch_applier.apply_queued_relationship_removals()
    await patch_applier.retry_deferred_operations()
    await patch_applier.apply_queued_attribute_removals()
    await patch_applier.retry_deferred_operations()
    if patch_log_record is not None:
        await emit("model_call_log", patch_log_record)
    parsed_operation_count = int(patch_applier.operation_count())
    await emit(
        "patch_operation_generation_done",
        patch_operation_generation_done_payload(
            raw_output=patch_completion.text,
            parsed_operation_count=parsed_operation_count,
            stream_parse_errors=stream_parse_errors,
            repair_reports=stream_parser.repair_reports,
        ),
    )
    operation_history.append(
        patch_operation_history_record(
            parsed_operation_count=parsed_operation_count,
            stream_parse_errors=stream_parse_errors,
        )
    )
    await checkpoint(
        "async-op-patch-after-patch-operations",
        checkpoint_payload(),
        "Async Operation Patch patch-operation checkpoint written.",
    )
    return completion_model


__all__ = ["PatchGenerationPhaseInput", "run_patch_generation_phase"]
