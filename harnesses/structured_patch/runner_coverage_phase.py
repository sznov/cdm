from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harnesses.structured_patch.coverage_phase import run_coverage_critic_phase
from harnesses.structured_patch.coverage_phase_types import RunnerCoveragePhaseInput
from harnesses.structured_patch.run_resume import ASYNC_OP_PATCH_RESUME_STAGES
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal
from harnesses.structured_patch.runner_operation_state import AsyncOpPatchOperationState


@dataclass(slots=True)
class RunnerCoveragePhaseResult:
    findings: list[dict[str, str]]
    decision_patches: list[dict[str, Any]]
    completion_model: str | None = None


async def run_resume_aware_coverage_phase(
    context: HarnessRunContext,
    phase_input: RunnerCoveragePhaseInput,
    journal: RunJournal,
    operation_state: AsyncOpPatchOperationState,
) -> RunnerCoveragePhaseResult:
    resume_payload = phase_input.resume_context.payload
    resume_order = phase_input.resume_context.order
    initial_phase = phase_input.initial_phase
    decision_patches = phase_input.decision_patches
    if resume_order >= ASYNC_OP_PATCH_RESUME_STAGES["async-op-patch-after-coverage-critic"]:
        return RunnerCoveragePhaseResult(
            findings=[item for item in resume_payload.get("findings", []) if isinstance(item, dict)],
            decision_patches=decision_patches,
        )

    coverage_result = await run_coverage_critic_phase(
        context,
        phase_input,
        journal,
        operation_state,
    )
    return RunnerCoveragePhaseResult(
        findings=coverage_result.findings,
        decision_patches=coverage_result.decision_patches,
        completion_model=coverage_result.completion_model,
    )


__all__ = [
    "RunnerCoveragePhaseInput",
    "RunnerCoveragePhaseResult",
    "run_resume_aware_coverage_phase",
]
