from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harnesses.structured_patch.events import structured_model_event_payload
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from core.schemas import StructuredModel

ASYNC_OP_PATCH_RESUME_STAGES = {
    "async-op-patch-after-draft": 10,
    "async-op-patch-after-language-repair": 20,
    "async-op-patch-after-coverage-critic": 30,
    "async-op-patch-after-patch-operations": 40,
    "structured-patch-base-complete": 40,
}


@dataclass
class StructuredPatchResumeContext:
    state: dict[str, Any] | None
    stage: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    order: int = 0
    structured_model: StructuredModel | None = None
    draft_model_issues: list[dict[str, Any]] = field(default_factory=list)
    draft_issue_decision_patches: list[dict[str, Any]] = field(default_factory=list)
    draft_issue_hard_findings: list[dict[str, str]] = field(default_factory=list)

    @property
    def enabled(self) -> bool:
        return self.order > 0

    @property
    def source_job_id(self) -> Any:
        return self.state.get("source_job_id") if self.state else None

    @property
    def checkpoint_path(self) -> Any:
        return self.state.get("checkpoint_path") if self.state else None


def parse_structured_patch_resume_context(
    resume_state: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> StructuredPatchResumeContext:
    state = resume_state if isinstance(resume_state, dict) else None
    if state is None:
        return StructuredPatchResumeContext(state=None)

    stage = str(state.get("stage") or "")
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    order = ASYNC_OP_PATCH_RESUME_STAGES.get(stage, 0)
    if not order:
        return StructuredPatchResumeContext(state=state, stage=stage, payload=payload, order=0)

    resume_model_payload = (
        state.get("structured_model")
        if isinstance(state.get("structured_model"), dict)
        else payload.get("structured_model")
        if isinstance(payload.get("structured_model"), dict)
        else payload
    )
    structured_model = StructuredModel.model_validate(resume_model_payload)
    name_policy.validate_model_names(structured_model)
    return StructuredPatchResumeContext(
        state=state,
        stage=stage,
        payload=payload,
        order=order,
        structured_model=structured_model,
        draft_model_issues=[item for item in payload.get("draft_model_issues", []) if isinstance(item, dict)],
        draft_issue_decision_patches=[
            item for item in payload.get("draft_issue_decision_patches", []) if isinstance(item, dict)
        ],
        draft_issue_hard_findings=[
            item for item in payload.get("draft_issue_hard_findings", []) if isinstance(item, dict)
        ],
    )


def resume_operation_history_record(context: StructuredPatchResumeContext) -> dict[str, Any]:
    return {
        "iteration": 1,
        "batch_attempt": 1,
        "accepted": [{"op": "RESUME_FROM_CHECKPOINT", "stage": context.stage}],
        "rejected": [],
        "focus": "Resume Async Operation Patch Model from latest sane structured-model snapshot.",
        "feedback": "",
        "resume_state": {
            "source_job_id": context.source_job_id,
            "stage": context.stage,
        },
    }


def resume_event_payload(context: StructuredPatchResumeContext) -> dict[str, Any]:
    if context.structured_model is None:
        raise ValueError("Cannot build resume event payload without a structured model.")
    return {
        "agent_id": "runtime",
        "source_job_id": context.source_job_id,
        "stage": context.stage,
        "checkpoint_path": context.checkpoint_path,
        "summary": f"Resuming Async Operation Patch Model from {context.stage}.",
        **structured_model_event_payload(context.structured_model),
    }


__all__ = [
    "ASYNC_OP_PATCH_RESUME_STAGES",
    "StructuredPatchResumeContext",
    "parse_structured_patch_resume_context",
    "resume_event_payload",
    "resume_operation_history_record",
]
