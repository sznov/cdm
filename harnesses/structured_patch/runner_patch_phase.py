from __future__ import annotations

from dataclasses import dataclass

from harnesses.structured_patch.patch_application_phase import StructuredPatchBatchApplier
from harnesses.structured_patch.patch_generation_phase import (
    PatchGenerationPhaseInput,
    run_patch_generation_phase,
)
from harnesses.structured_patch.run_resume import ASYNC_OP_PATCH_RESUME_STAGES, StructuredPatchResumeContext
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal
from harnesses.structured_patch.runner_coverage_phase import RunnerCoveragePhaseResult
from harnesses.structured_patch.runner_initial_phase import InitialStructuredModelPhaseResult
from harnesses.structured_patch.runner_operation_state import AsyncOpPatchOperationState


@dataclass(slots=True)
class PendingPatchOperationsPhaseInput:
    initial_phase: InitialStructuredModelPhaseResult
    coverage_result: RunnerCoveragePhaseResult
    resume_context: StructuredPatchResumeContext


@dataclass(slots=True)
class PendingPatchOperationsPhaseResult:
    completion_model: str | None = None


async def run_pending_patch_operations_phase(
    context: HarnessRunContext,
    phase_input: PendingPatchOperationsPhaseInput,
    journal: RunJournal,
    operation_state: AsyncOpPatchOperationState,
    patch_applier: StructuredPatchBatchApplier,
) -> PendingPatchOperationsPhaseResult:
    findings = phase_input.coverage_result.findings
    if not findings or phase_input.resume_context.order >= ASYNC_OP_PATCH_RESUME_STAGES["async-op-patch-after-patch-operations"]:
        return PendingPatchOperationsPhaseResult()

    completion_model = await run_patch_generation_phase(
        context,
        PatchGenerationPhaseInput(
            initial_phase=phase_input.initial_phase,
            findings=findings,
        ),
        journal,
        operation_state,
        patch_applier,
    )
    return PendingPatchOperationsPhaseResult(completion_model=completion_model)


__all__ = [
    "PendingPatchOperationsPhaseInput",
    "PendingPatchOperationsPhaseResult",
    "run_pending_patch_operations_phase",
]
