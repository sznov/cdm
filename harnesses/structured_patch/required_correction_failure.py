from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from core.model_call_logger import ModelCallLogger
from core.operation_loop_result import OperationLoopResult
from harnesses.structured_patch.required_correction_events import emit_new_model_call_logs
from harnesses.structured_patch.required_correction_provenance import (
    correction_phase_rejected_count,
    reconciled_operation_history,
)
from harnesses.structured_patch.required_correction_types import (
    CorrectionPhaseState,
    CorrectionTemplateIdentity,
    RequiredCorrectionPhaseError,
)
from harnesses.structured_patch.run_events import StructuredPatchRunEvents
from harnesses.structured_patch.name_policy import StructuredNamePolicy


ResultBuilder = Callable[..., OperationLoopResult]


async def build_required_correction_failure(
    *,
    stage: str,
    error: BaseException | str,
    phase_already_recorded: bool,
    base_result: OperationLoopResult,
    fallback_result: OperationLoopResult,
    state: CorrectionPhaseState,
    template: CorrectionTemplateIdentity,
    logger: ModelCallLogger,
    events: StructuredPatchRunEvents,
    result_builder: ResultBuilder,
    name_policy: StructuredNamePolicy,
) -> RequiredCorrectionPhaseError:
    """Assemble typed failure provenance after reconciling all visible outcomes."""

    detail = str(error) or repr(error)
    prior_history_count = len(state.operation_history)
    failure_iteration = base_result.iterations + max(1, len(state.phase_results) + 1)
    reconciled = reconciled_operation_history(
        operation_history=state.operation_history,
        applied_operations=state.applied_operations,
        already_satisfied_operations=state.already_satisfied_operations,
        rejected_operations=state.rejected_operations,
        deferred_operations=state.deferred_operations,
        iteration=failure_iteration,
        default_sequence=state.operation_sequence,
        normalize_from=prior_history_count,
        include_deferred=True,
        name_policy=name_policy,
    )
    state.operation_history[:] = reconciled.records
    await emit_new_model_call_logs(events=events, logger=logger, state=state)
    payload = {
        "job_id": base_result.job_id,
        "template_id": template.template_id,
        "template_name": template.template_name,
        "policy_id": template.policy_id,
        "status": "failed",
        "stage": stage,
        "error": detail,
        "phase_results": deepcopy(state.phase_results),
        "accepted_count": len(state.applied_operations) + len(state.already_satisfied_operations),
        "changed_count": len(state.applied_operations),
        "rejected_count": len(state.rejected_operations) + 1,
        "failure_count": 1,
        "deferred_count": len(state.deferred_operations),
        "deferred_operations": deepcopy(state.deferred_operations),
        "base_decision_patches": deepcopy(state.base_decision_patches),
        "diagnostic_decisions": {
            "decision_patches": deepcopy(state.decision_patches),
        },
        "pre_correction_checkpoint": deepcopy(state.pre_correction_checkpoint),
        "summary": f"Required correction failed during {stage}: {detail}",
    }
    failed_phase_count = len(state.phase_results) + (0 if phase_already_recorded else 1)
    state.operation_history.append(
        {
            "iteration": base_result.iterations + max(1, failed_phase_count),
            "batch_attempt": 1,
            "accepted": [],
            "rejected": [
                {
                    "op": "REQUIRED_GUARDED_CORRECTION",
                    "stage": stage,
                    "error": detail,
                }
            ],
            "focus": "Run the required post-hoc correction phase.",
            "feedback": detail,
        }
    )
    completion_record = {"kind": "correction_sequence", **payload}
    try:
        name_policy.validate_model_names(state.structured_model)
        diagnostic_partial_result = result_builder(
            base_result=base_result,
            state=state,
            completion_record=completion_record,
            logger=logger,
            phase_count=max(1, failed_phase_count),
            stop_reason="async_op_patch_model_required_correction_failed",
        )
    except Exception:
        # Rendering or validation can itself be the failing stage. Preserve
        # provenance while anchoring diagnostic artifacts to the safe base.
        diagnostic_partial_result = deepcopy(fallback_result)
        diagnostic_partial_result.operation_history = deepcopy(state.operation_history)
        diagnostic_partial_result.input_prompts = deepcopy(state.input_prompts)
        diagnostic_partial_result.completion_checks = [
            *deepcopy(base_result.completion_checks),
            completion_record,
        ]
        diagnostic_partial_result.model_call_logs = [
            *deepcopy(base_result.model_call_logs),
            *deepcopy(logger.records),
        ]
        diagnostic_partial_result.iterations = base_result.iterations + max(1, failed_phase_count)
        diagnostic_partial_result.rejected_operation_count = correction_phase_rejected_count(
            base_result=base_result,
            state=state,
        )
        diagnostic_partial_result.stop_reason = "async_op_patch_model_required_correction_failed"
        diagnostic_partial_result.model = state.completion_model
        diagnostic_partial_result.usage_steps = deepcopy(state.usage_steps)
    await events.emit("correction_sequence_failed", payload)
    return RequiredCorrectionPhaseError(
        payload["summary"],
        stage=stage,
        fallback_result=deepcopy(fallback_result),
        diagnostic_partial_result=diagnostic_partial_result,
        pre_correction_checkpoint=state.pre_correction_checkpoint,
        correction_sequence=payload,
    )


__all__ = ["ResultBuilder", "build_required_correction_failure"]
