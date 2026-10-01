from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from core.operation_loop_result import OperationLoopResult
from core.schemas import StructuredModel


@dataclass(frozen=True, slots=True)
class RequiredCorrectionPhaseResult:
    """Field-frozen boundary whose owned payloads are detached from inputs."""

    result: OperationLoopResult
    correction_sequence: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class RequiredCorrectionPhaseInput:
    specification: str
    result: OperationLoopResult
    correction_template_id: str
    max_operations: int | None


class RequiredCorrectionPhaseError(RuntimeError):
    """A required refined phase failed after producing a recoverable result."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        fallback_result: OperationLoopResult | None,
        diagnostic_partial_result: OperationLoopResult | None,
        pre_correction_checkpoint: dict[str, Any] | None,
        correction_sequence: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.fallback_result = fallback_result
        # Compatibility spelling remains safe for callers that persist it.
        self.partial_result = fallback_result
        self.diagnostic_partial_result = diagnostic_partial_result
        self.pre_correction_checkpoint = deepcopy(pre_correction_checkpoint)
        self.correction_sequence = deepcopy(correction_sequence)


@dataclass(frozen=True, slots=True)
class CorrectionTemplateIdentity:
    template_id: str
    template_name: str
    policy_id: str


@dataclass(frozen=True, slots=True)
class CorrectionStepInput:
    index: int
    count: int
    step_id: str
    name: str
    summary_label: str
    message: str
    allowed_ops: frozenset[str]

    def event_payload(self, *, job_id: str, template: CorrectionTemplateIdentity) -> dict[str, Any]:
        return {
            "job_id": job_id,
            "template_id": template.template_id,
            "template_name": template.template_name,
            "step_index": self.index,
            "step_count": self.count,
            "step_id": self.step_id,
            "step_name": self.name,
            "message": self.message,
            "allowed_ops": sorted(self.allowed_ops) if self.allowed_ops else None,
            "summary": f"Correction sequence step {self.index}/{self.count}: {self.summary_label}",
        }


@dataclass(frozen=True, slots=True)
class StepOutcomeBaseline:
    applied: int
    satisfied: int
    rejected: int
    deferred: int
    history: int
    deferred_signatures: frozenset[str]


@dataclass(frozen=True, slots=True)
class StepOutcomeSummary:
    accepted_count: int
    changed_count: int
    rejected_count: int
    deferred_count: int
    resolved_deferred_count: int
    remaining_deferred_count: int


@dataclass(slots=True)
class CorrectionPhaseState:
    """Mutable domain state for one ordered correction phase.

    Collaborators such as clients, event sinks, and persistence are deliberately
    excluded so this remains phase data rather than becoming a service locator.
    """

    structured_model: StructuredModel
    operation_history: list[dict[str, Any]]
    input_prompts: list[dict[str, Any]]
    usage_steps: list[dict[str, Any] | None]
    decision_patches: list[dict[str, Any]]
    base_decision_patches: list[dict[str, Any]]
    completion_model: str
    applied_operations: list[dict[str, Any]] = field(default_factory=list)
    rejected_operations: list[dict[str, Any]] = field(default_factory=list)
    already_satisfied_operations: list[dict[str, Any]] = field(default_factory=list)
    deferred_operations: list[dict[str, Any]] = field(default_factory=list)
    phase_results: list[dict[str, Any]] = field(default_factory=list)
    language_repair_record: dict[str, Any] | None = None
    language_repair_ran: bool = False
    emitted_log_count: int = 0
    diagnostic_snapshot_version: int = 0
    operation_sequence: int = 0
    deferred_retry_fingerprint: str | None = None
    pre_correction_checkpoint: dict[str, Any] | None = None


class CorrectionExecutionError(RuntimeError):
    """Internal stage marker; legacy callers still receive the original cause."""

    def __init__(
        self,
        stage: str,
        cause: BaseException | str,
        *,
        phase_already_recorded: bool = False,
    ) -> None:
        detail = str(cause) or repr(cause)
        super().__init__(detail)
        self.stage = stage
        self.cause = cause
        self.phase_already_recorded = phase_already_recorded


__all__ = [
    "CorrectionExecutionError",
    "CorrectionPhaseState",
    "CorrectionStepInput",
    "CorrectionTemplateIdentity",
    "RequiredCorrectionPhaseInput",
    "RequiredCorrectionPhaseResult",
    "RequiredCorrectionPhaseError",
    "StepOutcomeBaseline",
    "StepOutcomeSummary",
]
