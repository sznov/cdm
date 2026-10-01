from __future__ import annotations

from typing import Any

from core.model_client import ChatMessage
from harnesses.structured_patch.draft_prompts import SIMPLE_DRAFT_SYSTEM_PROMPT
from harnesses.structured_patch.events import structured_model_event_payload
from core.schemas import StructuredModel


def draft_prompt_input_payload(
    *,
    draft_messages: list[ChatMessage],
    max_attempts: int,
) -> dict[str, Any]:
    return {
        "agent_id": "draftModeler",
        "title": "Async patch draft model prompt",
        "summary": "Specification resolved into one broad draft-model prompt.",
        "system_prompt": SIMPLE_DRAFT_SYSTEM_PROMPT,
        "messages": [dict(message) for message in draft_messages],
        "max_attempts": max_attempts,
    }


def draft_generation_start_payload(*, attempt: int, max_attempts: int) -> dict[str, Any]:
    return {
        "agent_id": "draftModeler",
        "iteration": 1,
        "batch_attempt": attempt,
        "summary": f"Generating broad draft model, attempt {attempt} of {max_attempts}.",
    }


def draft_generation_delta_payload(*, attempt: int, delta: str) -> dict[str, Any]:
    return {
        "agent_id": "draftModeler",
        "batch_attempt": attempt,
        "delta": delta,
    }


def draft_generation_done_payload(*, attempt: int, raw_output: str) -> dict[str, Any]:
    return {
        "agent_id": "draftModeler",
        "batch_attempt": attempt,
        "raw_output": raw_output,
        "summary": f"Draft model output received for attempt {attempt}.",
    }


def draft_model_validation_success_payload(
    *,
    attempt: int,
    structured_model: StructuredModel,
    deterministic_repairs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "agent_id": "structuredValidator",
        "batch_attempt": attempt,
        "accepted": True,
        **structured_model_event_payload(structured_model),
        "deterministic_repairs": deterministic_repairs,
        "summary": f"{len(structured_model.entities)} entities, {len(structured_model.relationships)} relationships validated.",
    }


def draft_model_issues_payload(
    *,
    draft_model_issues: list[dict[str, Any]],
    draft_issue_decision_patches: list[dict[str, Any]],
    draft_issue_hard_findings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "agent_id": "draftModeler",
        "issues": draft_model_issues,
        "decision_patches": draft_issue_decision_patches,
        "hard_findings": draft_issue_hard_findings,
        "summary": f"Draft model reported {len(draft_model_issues)} issue(s).",
    }


def draft_model_success_history_record(
    *,
    attempt: int,
    structured_model: StructuredModel,
) -> dict[str, Any]:
    return {
        "iteration": 1,
        "batch_attempt": attempt,
        "accepted": [
            {
                "op": "STRUCTURED_MODEL",
                "entity_count": len(structured_model.entities),
                "relationship_count": len(structured_model.relationships),
            }
        ],
        "rejected": [],
        "focus": "Produce broad draft structured conceptual model.",
        "feedback": "",
    }


def draft_model_checkpoint_payload(
    *,
    structured_model: StructuredModel,
    draft_model_issues: list[dict[str, Any]],
    draft_issue_decision_patches: list[dict[str, Any]],
    draft_issue_hard_findings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "structured_model": structured_model.model_dump(mode="json"),
        "draft_model_issues": draft_model_issues,
        "draft_issue_decision_patches": draft_issue_decision_patches,
        "draft_issue_hard_findings": draft_issue_hard_findings,
    }


def draft_model_failure_history_record(
    *,
    attempt: int,
    error: str,
    raw_output: str,
) -> dict[str, Any]:
    return {
        "iteration": 1,
        "batch_attempt": attempt,
        "accepted": [],
        "rejected": [{"op": "STRUCTURED_MODEL", "error": error, "actual_raw_output": raw_output}],
        "focus": "Produce broad draft structured conceptual model.",
        "feedback": error,
    }


def draft_model_validation_failure_payload(
    *,
    attempt: int,
    error: str,
    max_attempts: int,
) -> dict[str, Any]:
    return {
        "agent_id": "structuredValidator",
        "batch_attempt": attempt,
        "accepted": False,
        "error": error,
        "summary": f"Draft model failed validation on attempt {attempt}.",
        "will_retry": attempt < max_attempts,
    }


def draft_model_retry_feedback_payload(
    *,
    attempt: int,
    feedback: str,
) -> dict[str, Any]:
    return {
        "agent_id": "structuredValidator",
        "batch_attempt": attempt,
        "next_attempt": attempt + 1,
        "feedback": feedback,
        "summary": f"Validation feedback appended to draft chat for attempt {attempt + 1}.",
    }


__all__ = [
    "draft_generation_delta_payload",
    "draft_generation_done_payload",
    "draft_generation_start_payload",
    "draft_model_checkpoint_payload",
    "draft_model_failure_history_record",
    "draft_model_issues_payload",
    "draft_model_retry_feedback_payload",
    "draft_model_success_history_record",
    "draft_model_validation_failure_payload",
    "draft_model_validation_success_payload",
    "draft_prompt_input_payload",
]
