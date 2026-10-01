from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harnesses.structured_patch.run_resume import StructuredPatchResumeContext
from harnesses.structured_patch.runner_initial_phase import InitialStructuredModelPhaseResult


@dataclass(slots=True)
class RunnerCoveragePhaseInput:
    initial_phase: InitialStructuredModelPhaseResult
    resume_context: StructuredPatchResumeContext
    decision_patches: list[dict[str, Any]]


@dataclass
class CoverageCriticPhaseResult:
    findings: list[dict[str, str]]
    decision_patches: list[dict[str, Any]]
    completion_model: str | None = None


__all__ = ["CoverageCriticPhaseResult", "RunnerCoveragePhaseInput"]
