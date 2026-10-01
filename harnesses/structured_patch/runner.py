from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.job_ids import make_job_id
from core.model_call_logger import ModelCallLogger
from core.model_client import TextModelClient
from core.operation_loop_result import OperationLoopResult
from harnesses.structured_patch.checkpoints import write_one_shot_run_checkpoint
from harnesses.structured_patch.language_repair_pass import run_structured_language_repair_pass
from harnesses.structured_patch.model_conversion import structured_model_to_working_model
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_application_phase import (
    StructuredPatchApplicationCallbacks,
    StructuredPatchApplicationPolicy,
    StructuredPatchApplicationState,
    StructuredPatchBatchApplier,
)
from harnesses.structured_patch.planning import (
    normalize_modeling_plan_payload,
    parse_modeling_plan_output,
    plan_task_count,
)
from harnesses.structured_patch.run_events import StructuredPatchRunEvents
from harnesses.structured_patch.run_finalization import finalize_async_op_patch_run
from harnesses.structured_patch.result_building import FinalizationInput
from harnesses.structured_patch.run_resume import (
    ASYNC_OP_PATCH_RESUME_STAGES,
    StructuredPatchResumeContext,
    parse_structured_patch_resume_context,
)
from harnesses.structured_patch.runner_context import (
    HarnessRunContext,
    HarnessRunInputs,
    ModelCallPolicy,
    RunJournal,
    StructuredPatchRunConfig,
)
from harnesses.structured_patch.runner_coverage_phase import (
    run_resume_aware_coverage_phase,
)
from harnesses.structured_patch.coverage_phase_types import RunnerCoveragePhaseInput
from harnesses.structured_patch.runner_decision_state import merged_decision_patches_from_resume_or_draft
from harnesses.structured_patch.runner_initial_phase import (
    InitialStructuredModelPhaseInput,
    prepare_initial_structured_model_phase,
)
from harnesses.structured_patch.runner_operation_state import operation_state_from_resume_payload
from harnesses.structured_patch.runner_patch_phase import (
    PendingPatchOperationsPhaseInput,
    run_pending_patch_operations_phase,
)
from harnesses.structured_patch.runner_post_patch_phase import run_post_patch_adjustments
from harnesses.structured_patch.runner_prompt_profile import (
    AsyncOpPatchPromptProfile,
    async_op_patch_prompt_profile,
)


def structured_patch_transport_retries(max_attempts: int | None = None) -> None:
    return None


@dataclass(slots=True)
class AsyncOpPatchExecution:
    context: HarnessRunContext
    resume_context: StructuredPatchResumeContext
    completion_model: str


async def _execute_async_op_patch_model(execution: AsyncOpPatchExecution) -> OperationLoopResult:
    """Execute the ordered phases from one immutable, materialized input."""

    context = execution.context
    journal = RunJournal()
    resume_payload = execution.resume_context.payload
    resume_order = execution.resume_context.order

    initial_phase = await prepare_initial_structured_model_phase(
        context,
        InitialStructuredModelPhaseInput(
            completion_model=execution.completion_model,
            resume_context=execution.resume_context,
        ),
        journal,
    )
    structured_model = initial_phase.structured_model
    draft_model_issues = initial_phase.draft_model_issues
    draft_issue_decision_patches = initial_phase.draft_issue_decision_patches
    draft_issue_hard_findings = initial_phase.draft_issue_hard_findings
    completion_model = initial_phase.completion_model

    operation_state = operation_state_from_resume_payload(
        resume_payload=resume_payload,
        resume_order=resume_order,
    )
    decision_patches = merged_decision_patches_from_resume_or_draft(
        resume_payload=resume_payload,
        resume_order=resume_order,
        draft_issue_decision_patches=draft_issue_decision_patches,
        name_policy=context.config.name_policy,
    )

    if not resume_order and (structured_model.entities or structured_model.relationships):
        await context.events.emit_partial_snapshot(structured_model, "Initial draft model rendered.")

    coverage_result = await run_resume_aware_coverage_phase(
        context,
        RunnerCoveragePhaseInput(
            initial_phase=initial_phase,
            resume_context=execution.resume_context,
            decision_patches=decision_patches,
        ),
        journal,
        operation_state,
    )
    findings = coverage_result.findings
    decision_patches = coverage_result.decision_patches
    if coverage_result.completion_model is not None:
        completion_model = coverage_result.completion_model

    patch_applier = StructuredPatchBatchApplier(
        specification=context.specification,
        state=StructuredPatchApplicationState(
            model=structured_model,
            decision_patches=decision_patches,
            applied_operations=operation_state.applied_operations,
            rejected_operations=operation_state.rejected_operations,
            already_satisfied_operations=operation_state.already_satisfied_operations,
            deferred_operations=operation_state.deferred_operations,
            operation_history=journal.operation_history,
        ),
        callbacks=StructuredPatchApplicationCallbacks(
            emit=context.events.emit,
            emit_partial_snapshot=context.events.emit_partial_snapshot,
        ),
        policy=StructuredPatchApplicationPolicy(name_policy=context.config.name_policy),
    )

    patch_result = await run_pending_patch_operations_phase(
        context,
        PendingPatchOperationsPhaseInput(
            initial_phase=initial_phase,
            coverage_result=coverage_result,
            resume_context=execution.resume_context,
        ),
        journal,
        operation_state,
        patch_applier,
    )
    if patch_result.completion_model is not None:
        completion_model = patch_result.completion_model

    post_patch_result = await run_post_patch_adjustments(
        context,
        patch_applier,
        journal,
        operation_state,
    )

    return await finalize_async_op_patch_run(
        context,
        FinalizationInput(
            initial_phase=initial_phase,
            coverage_result=coverage_result,
            post_patch_result=post_patch_result,
            completion_model=completion_model,
        ),
        journal,
        operation_state,
    )


async def run_async_op_patch_model(
    *,
    specification: str,
    client: TextModelClient,
    max_attempts: int = 3,
    infer_implicit_identifiers: bool = False,
    structured_language_repair: bool = False,
    direct_microop_judge: bool = False,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
    job_id: str | None = None,
    model_call_log_dir: Path | None = None,
    resume_state: dict[str, Any] | None = None,
    on_event: Any | None = None,
) -> OperationLoopResult:
    """Compatibility entrypoint around the typed one-input executor."""

    run_job_id = job_id or make_job_id()
    logger = ModelCallLogger(job_id=run_job_id, log_dir=model_call_log_dir)
    events = StructuredPatchRunEvents(
        job_id=run_job_id,
        model_call_log_dir=model_call_log_dir,
        on_event=on_event,
    )
    resolved_max_attempts = max(1, int(max_attempts or 1))
    run_config = StructuredPatchRunConfig(
        model_calls=ModelCallPolicy(
            max_attempts=resolved_max_attempts,
            transport_retries=structured_patch_transport_retries(resolved_max_attempts),
        ),
        infer_implicit_identifiers=bool(infer_implicit_identifiers),
        structured_language_repair=bool(structured_language_repair),
        direct_microop_judge=bool(direct_microop_judge),
        prompt_profile=async_op_patch_prompt_profile(
            direct_microop_judge=bool(direct_microop_judge),
            name_policy=name_policy,
        ),
        name_policy=name_policy,
    )
    context = HarnessRunContext(
        inputs=HarnessRunInputs(
            specification=specification,
            run_job_id=run_job_id,
            model_call_log_dir=model_call_log_dir,
            config=run_config,
        ),
        client=client,
        logger=logger,
        events=events,
    )
    return await _execute_async_op_patch_model(
        AsyncOpPatchExecution(
            context=context,
            resume_context=parse_structured_patch_resume_context(
                resume_state,
                name_policy=name_policy,
            ),
            completion_model=str(getattr(client, "model", "unknown")),
        )
    )


__all__ = [
    "ASYNC_OP_PATCH_RESUME_STAGES",
    "AsyncOpPatchExecution",
    "normalize_modeling_plan_payload",
    "parse_modeling_plan_output",
    "plan_task_count",
    "run_async_op_patch_model",
    "run_structured_language_repair_pass",
    "structured_patch_transport_retries",
    "structured_model_to_working_model",
    "write_one_shot_run_checkpoint",
]
