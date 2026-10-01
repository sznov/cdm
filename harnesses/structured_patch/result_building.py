from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.operation_loop_result import OperationLoopResult
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal
from harnesses.structured_patch.runner_coverage_phase import RunnerCoveragePhaseResult
from harnesses.structured_patch.runner_initial_phase import InitialStructuredModelPhaseResult
from harnesses.structured_patch.runner_operation_state import AsyncOpPatchOperationState
from harnesses.structured_patch.runner_post_patch_phase import PostPatchAdjustmentResult


@dataclass(slots=True)
class FinalizationInput:
    initial_phase: InitialStructuredModelPhaseResult
    coverage_result: RunnerCoveragePhaseResult
    post_patch_result: PostPatchAdjustmentResult
    completion_model: str


def structured_patch_rejected_count(
    *,
    operation_history: list[dict[str, Any]],
    rejected_operations: list[dict[str, Any]],
) -> int:
    return len(rejected_operations) + sum(
        len(item.get("rejected") or [])
        for item in operation_history
        if not any(
            isinstance(rejected, dict) and rejected.get("result") in rejected_operations
            for rejected in item.get("rejected") or []
        )
    )


def build_async_op_patch_result(
    context: HarnessRunContext,
    phase_input: FinalizationInput,
    journal: RunJournal,
    operation_state: AsyncOpPatchOperationState,
    working_model: Any,
    plantuml: str,
) -> OperationLoopResult:
    structured_model = phase_input.post_patch_result.structured_model
    decision_patches = phase_input.post_patch_result.decision_patches
    initial_phase = phase_input.initial_phase
    findings = phase_input.coverage_result.findings
    return OperationLoopResult(
        job_id=context.inputs.run_job_id,
        working_model=working_model,
        structured_model=structured_model,
        plantuml=plantuml,
        plantuml_url="",
        operation_history=journal.operation_history,
        input_prompts=journal.input_prompts,
        completion_checks=[
            *(
                [
                    {
                        "kind": "draft_model_issues",
                        "issues": initial_phase.draft_model_issues,
                        "decision_patches": initial_phase.draft_issue_decision_patches,
                        "hard_findings": initial_phase.draft_issue_hard_findings,
                    }
                ]
                if initial_phase.draft_model_issues
                else []
            ),
            {
                "kind": "coverage_critic",
                "finding_count": len(findings),
                "findings": findings,
                "decision_patches": decision_patches,
            },
        ],
        plan_updates=[],
        model_call_log_dir=(
            str(context.inputs.model_call_log_dir)
            if context.inputs.model_call_log_dir is not None
            else None
        ),
        model_call_logs=context.logger.records,
        iterations=max(1, len(journal.operation_history)),
        accepted_operation_count=1 + len(operation_state.applied_operations),
        rejected_operation_count=structured_patch_rejected_count(
            operation_history=journal.operation_history,
            rejected_operations=operation_state.rejected_operations,
        ),
        stop_reason="async_op_patch_model_complete",
        model=phase_input.completion_model,
        usage_steps=journal.usage_steps,
    )


__all__ = [
    "FinalizationInput",
    "build_async_op_patch_result",
    "structured_patch_rejected_count",
]
