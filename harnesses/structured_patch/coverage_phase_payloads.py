from __future__ import annotations

import json
from typing import Any

from core.model_client import ChatMessage
from harnesses.structured_patch.coverage_prompts import PLAN_COVERAGE_CRITIC_SYSTEM_PROMPT
from core.schemas import StructuredModel


def fallback_modeling_plan_json() -> str:
    fallback_plan = {
        "phases": [
            {
                "id": "P1",
                "name": "Full specification coverage",
                "goal": "Check the current draft against the full specification.",
                "tasks": [
                    {
                        "id": "T1",
                        "kind": "other",
                        "concept": "FullSpecification",
                        "participants": [],
                        "evidence": "",
                        "note": "Use the specification as the source of truth for coverage critique.",
                    }
                ],
            }
        ],
        "open_questions": [],
    }
    return json.dumps(fallback_plan, ensure_ascii=False, indent=2)


def coverage_critic_prompt_payload(*, critic_messages: list[ChatMessage]) -> dict[str, Any]:
    return {
        "agent_id": "planCoverageCritic",
        "title": "Async patch coverage critic prompt",
        "summary": "Specification and current draft resolved into a coverage critic prompt.",
        "system_prompt": PLAN_COVERAGE_CRITIC_SYSTEM_PROMPT,
        "messages": [dict(message) for message in critic_messages],
    }


def coverage_critic_start_payload() -> dict[str, Any]:
    return {
        "agent_id": "planCoverageCritic",
        "iteration": 3,
        "summary": "Critiquing broad draft model for missing or weak artifacts.",
    }


def coverage_critic_delta_payload(*, delta: str) -> dict[str, Any]:
    return {"agent_id": "planCoverageCritic", "delta": delta}


def coverage_critic_done_payload(*, raw_output: str) -> dict[str, Any]:
    return {
        "agent_id": "planCoverageCritic",
        "raw_output": raw_output,
        "summary": "Coverage critic output received.",
    }


def coverage_critic_success_history_record(*, critic_finding_count: int) -> dict[str, Any]:
    return {
        "iteration": 3,
        "batch_attempt": 1,
        "accepted": [{"op": "COVERAGE_CRITIC", "finding_count": critic_finding_count}],
        "rejected": [],
        "focus": "Critique current draft against the specification.",
        "feedback": "",
    }


def coverage_critic_result_payload(
    *,
    findings: list[dict[str, str]],
    critic_findings: list[dict[str, str]],
    draft_issue_hard_findings: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "agent_id": "planCoverageCritic",
        "finding_count": len(findings),
        "critic_finding_count": len(critic_findings),
        "draft_hard_finding_count": len(draft_issue_hard_findings),
        "findings": findings,
        "summary": f"Coverage critic produced {len(critic_findings)} finding(s); {len(findings)} total finding(s).",
    }


def coverage_decision_patches_payload(*, decision_patches: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "agent_id": "planCoverageCritic",
        "decision_patches": decision_patches,
        "summary": f"{len(decision_patches)} user decision patch(es) available.",
    }


def coverage_checkpoint_payload(
    *,
    structured_model: StructuredModel,
    draft_model_issues: list[dict[str, Any]],
    draft_issue_decision_patches: list[dict[str, Any]],
    draft_issue_hard_findings: list[dict[str, str]],
    findings: list[dict[str, str]],
    decision_patches: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "structured_model": structured_model.model_dump(mode="json"),
        "draft_model_issues": draft_model_issues,
        "draft_issue_decision_patches": draft_issue_decision_patches,
        "draft_issue_hard_findings": draft_issue_hard_findings,
        "findings": findings,
        "decision_patches": decision_patches,
    }


def coverage_critic_failure_history_record(*, error: str) -> dict[str, Any]:
    return {
        "iteration": 3,
        "batch_attempt": 1,
        "accepted": [],
        "rejected": [{"op": "COVERAGE_CRITIC", "error": error}],
        "focus": "Critique current draft against the specification.",
        "feedback": error,
    }


def coverage_critic_failure_result_payload(*, error: str) -> dict[str, Any]:
    return {
        "agent_id": "planCoverageCritic",
        "finding_count": 0,
        "findings": [],
        "error": error,
        "summary": f"Coverage critic failed: {error}",
    }


__all__ = [
    "coverage_checkpoint_payload",
    "coverage_critic_delta_payload",
    "coverage_critic_done_payload",
    "coverage_critic_failure_history_record",
    "coverage_critic_failure_result_payload",
    "coverage_critic_prompt_payload",
    "coverage_critic_result_payload",
    "coverage_critic_start_payload",
    "coverage_critic_success_history_record",
    "coverage_decision_patches_payload",
    "fallback_modeling_plan_json",
]
