from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Never

from core.model_call_logger import ModelCallLogger
from core.model_client import TextModelClient
from core.operation_loop_result import OperationLoopResult
from harnesses.structured_patch.checkpoints import write_one_shot_run_checkpoint
from harnesses.structured_patch.correction_policy import CorrectionPhasePolicy
from harnesses.structured_patch.correction_templates import correction_template_by_id
from harnesses.structured_patch.events import structured_model_event_payload
from harnesses.structured_patch.required_correction_failure import build_required_correction_failure
from harnesses.structured_patch.required_correction_provenance import (
    build_correction_result,
    build_done_payload,
    initialize_phase_state,
    model_call_log_counter,
    reconciled_operation_history,
)
from harnesses.structured_patch.required_correction_step import (
    correction_step_input,
    execute_correction_step,
)
from harnesses.structured_patch.required_correction_types import (
    CorrectionExecutionError,
    CorrectionPhaseState,
    CorrectionTemplateIdentity,
    RequiredCorrectionPhaseInput,
    RequiredCorrectionPhaseResult,
    RequiredCorrectionPhaseError,
)
from harnesses.structured_patch.patch_application_phase import StructuredPatchBatchApplier
from harnesses.structured_patch.run_events import StructuredPatchRunEvents


PRE_CORRECTION_CHECKPOINT_STAGE = "structured-patch-base-complete"
POST_CORRECTION_CHECKPOINT_STAGE = "structured-patch-posthoc-correction"

# Compatibility seams retained for focused fault-injection tests and callers
# that have historically patched these module-local helpers.
_build_result = build_correction_result


def required_correction_configuration_error(correction_template_id: str) -> str | None:
    template = correction_template_by_id(correction_template_id)
    if template is None:
        return f"Unknown correction template: {correction_template_id}"
    executable_steps = [
        step
        for step in template.get("steps") or []
        if isinstance(step, dict) and str(step.get("message") or "").strip()
    ]
    if not executable_steps:
        return "Required correction template has no executable steps."
    return None


def preexecution_required_correction_error(
    *,
    correction_template_id: str,
    policy: CorrectionPhasePolicy,
    error: str,
) -> RequiredCorrectionPhaseError:
    payload = {
        "template_id": correction_template_id,
        "policy_id": policy.policy_id,
        "status": "failed",
        "stage": "correction_configuration",
        "error": error,
        "pre_execution": True,
        "accepted_count": 0,
        "changed_count": 0,
        "rejected_count": 0,
        "deferred_count": 0,
        "failure_count": 1,
        "pre_correction_checkpoint": None,
        "summary": f"Required correction configuration is invalid: {error}",
    }
    return RequiredCorrectionPhaseError(
        payload["summary"],
        stage="correction_configuration",
        fallback_result=None,
        diagnostic_partial_result=None,
        pre_correction_checkpoint=None,
        correction_sequence=payload,
    )


def _write_checkpoint(
    *,
    model_call_log_dir: Path | None,
    job_id: str,
    stage: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    return write_one_shot_run_checkpoint(
        model_call_log_dir,
        job_id=job_id,
        stage=stage,
        payload=payload,
    )


async def _notify_checkpoint_written(
    *,
    events: StructuredPatchRunEvents,
    checkpoint_record: dict[str, Any] | None,
    summary: str,
) -> None:
    if checkpoint_record is not None:
        await events.emit(
            "checkpoint_written",
            {"agent_id": "runtime", **checkpoint_record, "summary": summary},
        )


async def _raise_required_failure(
    *,
    execution_error: CorrectionExecutionError,
    result: OperationLoopResult,
    fallback_result: OperationLoopResult,
    state: CorrectionPhaseState,
    template: CorrectionTemplateIdentity,
    logger: ModelCallLogger,
    events: StructuredPatchRunEvents,
    policy: CorrectionPhasePolicy,
) -> Never:
    cause = execution_error.cause
    if not policy.refined:
        if isinstance(cause, BaseException):
            raise cause
        raise RuntimeError(str(cause))
    failure = await build_required_correction_failure(
        stage=execution_error.stage,
        error=cause,
        phase_already_recorded=execution_error.phase_already_recorded,
        base_result=result,
        fallback_result=fallback_result,
        state=state,
        template=template,
        logger=logger,
        events=events,
        result_builder=_build_result,
        name_policy=policy.name_policy,
    )
    if isinstance(cause, BaseException):
        raise failure from cause
    raise failure


async def _checkpoint_pre_correction_result(
    *,
    result: OperationLoopResult,
    fallback_result: OperationLoopResult,
    state: CorrectionPhaseState,
    template: CorrectionTemplateIdentity,
    logger: ModelCallLogger,
    events: StructuredPatchRunEvents,
    policy: CorrectionPhasePolicy,
    model_call_log_dir: Path | None,
) -> None:
    if not policy.refined:
        return
    try:
        state.pre_correction_checkpoint = _write_checkpoint(
            model_call_log_dir=model_call_log_dir,
            job_id=result.job_id,
            stage=PRE_CORRECTION_CHECKPOINT_STAGE,
            payload={
                "structured_model": fallback_result.structured_model.model_dump(mode="json"),
                "result": fallback_result.to_dict(),
                "decision_patches": state.decision_patches,
            },
        )
    except Exception as exc:
        await _raise_required_failure(
            execution_error=CorrectionExecutionError("pre_correction_checkpoint", exc),
            result=result,
            fallback_result=fallback_result,
            state=state,
            template=template,
            logger=logger,
            events=events,
            policy=policy,
        )
    # Observation happens after the atomic commit and therefore is not relabelled.
    await _notify_checkpoint_written(
        events=events,
        checkpoint_record=state.pre_correction_checkpoint,
        summary="Usable pre-post-hoc structured patch checkpoint written.",
    )


async def _finalize_correction(
    *,
    result: OperationLoopResult,
    fallback_result: OperationLoopResult,
    state: CorrectionPhaseState,
    template: CorrectionTemplateIdentity,
    logger: ModelCallLogger,
    events: StructuredPatchRunEvents,
    policy: CorrectionPhasePolicy,
    model_call_log_dir: Path | None,
) -> RequiredCorrectionPhaseResult:
    if policy.refined:
        reconciled = reconciled_operation_history(
            operation_history=state.operation_history,
            applied_operations=state.applied_operations,
            already_satisfied_operations=state.already_satisfied_operations,
            rejected_operations=state.rejected_operations,
            deferred_operations=state.deferred_operations,
            iteration=result.iterations + max(1, len(state.phase_results)),
            default_sequence=state.operation_sequence,
            normalize_from=len(state.operation_history),
            include_deferred=True,
            name_policy=policy.name_policy,
        )
        state.operation_history[:] = reconciled.records
    done_payload = build_done_payload(
        job_id=result.job_id,
        template_id=template.template_id,
        template_name=template.template_name,
        policy_id=template.policy_id,
        state=state,
        refined=policy.refined,
        checkpoint_stage=POST_CORRECTION_CHECKPOINT_STAGE,
    )
    try:
        policy.name_policy.validate_model_names(state.structured_model)
        corrected = _build_result(
            base_result=result,
            state=state,
            completion_record={"kind": "correction_sequence", **done_payload},
            logger=logger,
            phase_count=len(state.phase_results),
            stop_reason=policy.success_stop_reason,
        )
    except Exception as exc:
        await _raise_required_failure(
            execution_error=CorrectionExecutionError("posthoc_correction_result_validation", exc),
            result=result,
            fallback_result=fallback_result,
            state=state,
            template=template,
            logger=logger,
            events=events,
            policy=policy,
        )
    try:
        checkpoint = _write_checkpoint(
            model_call_log_dir=model_call_log_dir,
            job_id=result.job_id,
            stage=POST_CORRECTION_CHECKPOINT_STAGE,
            payload=structured_model_event_payload(state.structured_model),
        )
    except Exception as exc:
        await _raise_required_failure(
            execution_error=CorrectionExecutionError("posthoc_correction_checkpoint", exc),
            result=result,
            fallback_result=fallback_result,
            state=state,
            template=template,
            logger=logger,
            events=events,
            policy=policy,
        )
    await _notify_checkpoint_written(
        events=events,
        checkpoint_record=checkpoint,
        summary="Structured patch post-hoc correction checkpoint written.",
    )
    await events.emit("correction_sequence_done", done_payload)
    final_payload: dict[str, Any] = {
        "agent_id": "structuredValidator",
        "entity_count": len(state.structured_model.entities),
        "relationship_count": len(state.structured_model.relationships),
        "summary": "Final structured model after post-hoc correction sequence.",
        **structured_model_event_payload(state.structured_model),
        "correction_sequence": done_payload,
    }
    if policy.refined:
        final_payload["decision_patches"] = deepcopy(state.decision_patches)
    await events.emit("structured_model_validated", final_payload)
    await events.emit(
        "working_model",
        {
            "working_model": corrected.working_model.model_dump(mode="json"),
            "model": corrected.working_model.model_dump(mode="json"),
        },
    )
    await events.emit(
        "plantuml_preview",
        {"plantuml": corrected.plantuml, "plantuml_url": corrected.plantuml_url},
    )
    return RequiredCorrectionPhaseResult(result=corrected, correction_sequence=deepcopy(done_payload))


async def run_required_correction_phase(
    phase_input: RequiredCorrectionPhaseInput,
    *,
    client: TextModelClient,
    model_call_log_dir: Path | None,
    transport_retries: int | None,
    policy: CorrectionPhasePolicy,
    on_event: Any | None,
) -> RequiredCorrectionPhaseResult:
    """Run the explicit ordered correction protocol for one completed base run."""

    specification = phase_input.specification
    result = phase_input.result
    correction_template_id = phase_input.correction_template_id
    max_operations = phase_input.max_operations
    resolved_template = correction_template_by_id(correction_template_id)
    if resolved_template is None and not policy.refined:
        raise ValueError(f"Unknown correction template: {correction_template_id}")
    steps = [
        step
        for step in (resolved_template or {}).get("steps") or []
        if isinstance(step, dict)
    ]
    if resolved_template is not None and not steps and not policy.refined:
        return RequiredCorrectionPhaseResult(result=result, correction_sequence=None)
    template_data = resolved_template or {
        "id": correction_template_id,
        "name": correction_template_id,
        "steps": [],
    }
    template = CorrectionTemplateIdentity(
        template_id=str(template_data["id"]),
        template_name=str(template_data.get("name") or template_data["id"]),
        policy_id=policy.policy_id,
    )
    configuration_error = (
        required_correction_configuration_error(correction_template_id)
        if policy.refined
        else None
    )
    events = StructuredPatchRunEvents(
        job_id=result.job_id,
        model_call_log_dir=model_call_log_dir,
        on_event=on_event,
    )
    fallback_result = deepcopy(result)
    state = initialize_phase_state(
        result,
        canonicalize_latest_decision_state=policy.refined,
        name_policy=policy.name_policy,
    )
    logger = ModelCallLogger(
        job_id=result.job_id,
        log_dir=model_call_log_dir,
        counter=model_call_log_counter(model_call_log_dir),
    )
    await _checkpoint_pre_correction_result(
        result=result,
        fallback_result=fallback_result,
        state=state,
        template=template,
        logger=logger,
        events=events,
        policy=policy,
        model_call_log_dir=model_call_log_dir,
    )
    if configuration_error is not None:
        await _raise_required_failure(
            execution_error=CorrectionExecutionError("correction_configuration", configuration_error),
            result=result,
            fallback_result=fallback_result,
            state=state,
            template=template,
            logger=logger,
            events=events,
            policy=policy,
        )
    await events.emit(
        "correction_sequence_start",
        {
            "job_id": result.job_id,
            "template_id": template.template_id,
            "template_name": template.template_name,
            "step_count": len(steps),
            "steps": steps,
            "summary": f"Running correction sequence: {template.template_name}.",
        },
    )
    for index, raw_step in enumerate(steps, start=1):
        step = correction_step_input(raw_step, index=index, count=len(steps))
        if not step.message:
            continue
        try:
            await execute_correction_step(
                step=step,
                template=template,
                specification=specification,
                state=state,
                base_iterations=result.iterations,
                client=client,
                logger=logger,
                events=events,
                policy=policy,
                max_operations=max_operations,
                transport_retries=transport_retries,
                applier_type=StructuredPatchBatchApplier,
            )
        except CorrectionExecutionError as exc:
            await _raise_required_failure(
                execution_error=exc,
                result=result,
                fallback_result=fallback_result,
                state=state,
                template=template,
                logger=logger,
                events=events,
                policy=policy,
            )
    return await _finalize_correction(
        result=result,
        fallback_result=fallback_result,
        state=state,
        template=template,
        logger=logger,
        events=events,
        policy=policy,
        model_call_log_dir=model_call_log_dir,
    )


__all__ = [
    "RequiredCorrectionPhaseResult",
    "POST_CORRECTION_CHECKPOINT_STAGE",
    "PRE_CORRECTION_CHECKPOINT_STAGE",
    "RequiredCorrectionPhaseError",
    "RequiredCorrectionPhaseInput",
    "preexecution_required_correction_error",
    "required_correction_configuration_error",
    "run_required_correction_phase",
]
