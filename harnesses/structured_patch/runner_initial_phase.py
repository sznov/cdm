from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harnesses.structured_patch.draft_phase import run_draft_model_phase
from harnesses.structured_patch.language_repair_pass import run_structured_language_repair_pass
from harnesses.structured_patch.run_resume import (
    ASYNC_OP_PATCH_RESUME_STAGES,
    StructuredPatchResumeContext,
    resume_event_payload,
    resume_operation_history_record,
)
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal
from harnesses.structured_patch.validation import run_hierarchy_identity_validation
from core.schemas import StructuredModel


@dataclass(slots=True)
class InitialStructuredModelPhaseInput:
    completion_model: str
    resume_context: StructuredPatchResumeContext


@dataclass(slots=True)
class DraftAssessment:
    draft_model_issues: list[dict[str, Any]]
    draft_issue_decision_patches: list[dict[str, Any]]
    draft_issue_hard_findings: list[dict[str, str]]


@dataclass(slots=True)
class InitialStructuredModelPhaseResult:
    structured_model: StructuredModel
    draft: DraftAssessment
    completion_model: str

    @property
    def draft_model_issues(self) -> list[dict[str, Any]]:
        return self.draft.draft_model_issues

    @property
    def draft_issue_decision_patches(self) -> list[dict[str, Any]]:
        return self.draft.draft_issue_decision_patches

    @property
    def draft_issue_hard_findings(self) -> list[dict[str, str]]:
        return self.draft.draft_issue_hard_findings


async def prepare_initial_structured_model_phase(
    context: HarnessRunContext,
    phase_input: InitialStructuredModelPhaseInput,
    journal: RunJournal,
) -> InitialStructuredModelPhaseResult:
    specification = context.specification
    client = context.client
    logger = context.logger
    transport_retries = context.config.model_calls.transport_retries
    emit = context.events.emit
    checkpoint = context.events.checkpoint
    structured_language_repair = context.config.structured_language_repair
    completion_model = phase_input.completion_model
    resume_context = phase_input.resume_context
    input_prompts = journal.input_prompts
    operation_history = journal.operation_history
    usage_steps = journal.usage_steps
    structured_model: StructuredModel | None = None
    draft_model_issues: list[dict[str, Any]] = []
    draft_issue_decision_patches: list[dict[str, Any]] = []
    draft_issue_hard_findings: list[dict[str, str]] = []
    resume_order = resume_context.order

    if resume_context.enabled:
        structured_model = resume_context.structured_model
        draft_model_issues = resume_context.draft_model_issues
        draft_issue_decision_patches = resume_context.draft_issue_decision_patches
        draft_issue_hard_findings = resume_context.draft_issue_hard_findings
        operation_history.append(resume_operation_history_record(resume_context))
        await emit("resume_from_checkpoint", resume_event_payload(resume_context))

    if structured_model is None:
        draft_result = await run_draft_model_phase(context, journal)
        structured_model = draft_result.structured_model
        draft_model_issues = draft_result.draft_model_issues
        draft_issue_decision_patches = draft_result.draft_issue_decision_patches
        draft_issue_hard_findings = draft_result.draft_issue_hard_findings
        if draft_result.completion_model is not None:
            completion_model = draft_result.completion_model

    if structured_model is None:
        structured_model = StructuredModel(entities=[], relationships=[])

    if (
        structured_language_repair
        and structured_model.entities
        and resume_order < ASYNC_OP_PATCH_RESUME_STAGES["async-op-patch-after-language-repair"]
    ):
        structured_model, initial_language_repair_event = await run_structured_language_repair_pass(
            specification=specification,
            structured_model=structured_model,
            client=client,
            logger=logger,
            harness="async-op-patch-model",
            stage="structured_language_repair",
            title="Async patch language repair prompt",
            prompt_summary="Validated async draft resolved into a name-only language repair prompt.",
            start_summary="Checking async draft model names against the specification language.",
            iteration=2,
            emit=emit,
            input_prompts=input_prompts,
            operation_history=operation_history,
            usage_steps=usage_steps,
            transport_retries=transport_retries,
        )
        if initial_language_repair_event.get("completion_model"):
            completion_model = str(initial_language_repair_event["completion_model"])

    hierarchy_identity_checked = False
    if structured_model.entities and resume_order < ASYNC_OP_PATCH_RESUME_STAGES["async-op-patch-after-language-repair"]:
        hierarchy_identity_checked = True
        (
            draft_model_issues,
            draft_issue_decision_patches,
            draft_issue_hard_findings,
            _hierarchy_identity_event,
        ) = await run_hierarchy_identity_validation(
            structured_model=structured_model,
            draft_model_issues=draft_model_issues,
            draft_issue_decision_patches=draft_issue_decision_patches,
            draft_issue_hard_findings=draft_issue_hard_findings,
            emit=emit,
            name_policy=context.config.name_policy,
        )
        await checkpoint(
            "async-op-patch-after-language-repair",
            {
                "structured_model": structured_model.model_dump(mode="json"),
                "draft_model_issues": draft_model_issues,
                "draft_issue_decision_patches": draft_issue_decision_patches,
                "draft_issue_hard_findings": draft_issue_hard_findings,
            },
            "Async Operation Patch language-repair checkpoint written.",
        )

    if (
        structured_model.entities
        and not hierarchy_identity_checked
        and not any(str(issue.get("id") or "").startswith("HID") for issue in draft_model_issues)
    ):
        (
            draft_model_issues,
            draft_issue_decision_patches,
            draft_issue_hard_findings,
            _hierarchy_identity_event,
        ) = await run_hierarchy_identity_validation(
            structured_model=structured_model,
            draft_model_issues=draft_model_issues,
            draft_issue_decision_patches=draft_issue_decision_patches,
            draft_issue_hard_findings=draft_issue_hard_findings,
            emit=emit,
            name_policy=context.config.name_policy,
        )

    return InitialStructuredModelPhaseResult(
        structured_model=structured_model,
        draft=DraftAssessment(
            draft_model_issues=draft_model_issues,
            draft_issue_decision_patches=draft_issue_decision_patches,
            draft_issue_hard_findings=draft_issue_hard_findings,
        ),
        completion_model=completion_model,
    )


__all__ = [
    "DraftAssessment",
    "InitialStructuredModelPhaseInput",
    "InitialStructuredModelPhaseResult",
    "prepare_initial_structured_model_phase",
]
