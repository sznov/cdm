from __future__ import annotations

from typing import Any

from core.model_client import ChatMessage


def structured_language_repair_prompt_payload(
    *,
    title: str,
    prompt_summary: str,
    system_prompt: str,
    repair_messages: list[ChatMessage],
) -> dict[str, Any]:
    return {
        "agent_id": "structuredLanguageRepair",
        "title": title,
        "summary": prompt_summary,
        "system_prompt": system_prompt,
        "messages": [dict(message) for message in repair_messages],
    }


def structured_language_repair_start_payload(
    *,
    iteration: int,
    stage: str,
    start_summary: str,
) -> dict[str, Any]:
    return {
        "agent_id": "structuredLanguageRepair",
        "iteration": iteration,
        "stage": stage,
        "summary": start_summary,
    }


def structured_language_repair_delta_payload(*, stage: str, delta: str) -> dict[str, Any]:
    return {"agent_id": "structuredLanguageRepair", "stage": stage, "delta": delta}


def structured_language_repair_done_payload(*, stage: str, raw_output: str) -> dict[str, Any]:
    return {
        "agent_id": "structuredLanguageRepair",
        "stage": stage,
        "raw_output": raw_output,
        "summary": "Structured language repair output received.",
    }


def structured_language_repair_success_history_record(
    *,
    iteration: int,
    stage: str,
    renames: list[dict[str, Any]],
    accepted_renames: list[dict[str, Any]],
    rejected_renames: list[dict[str, Any]],
    applied_count: int,
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "batch_attempt": 1,
        "accepted": [
            {
                "op": "STRUCTURED_LANGUAGE_REPAIR",
                "stage": stage,
                "rename_count": len(renames),
                "accepted_rename_count": len(accepted_renames),
                "rejected_rename_count": len(rejected_renames),
                "applied_count": applied_count,
                "rejected_renames": rejected_renames,
            }
        ],
        "rejected": [],
        "focus": "Repair structured model names to match the specification language.",
        "feedback": "",
    }


def structured_language_repair_success_event_payload(
    *,
    stage: str,
    completion_model: str | None,
    applied_count: int,
    renames: list[dict[str, Any]],
    accepted_renames: list[dict[str, Any]],
    rejected_renames: list[dict[str, Any]],
    applied_renames: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "agent_id": "structuredLanguageRepair",
        "stage": stage,
        "completion_model": completion_model,
        "applied_count": applied_count,
        "accepted_rename_count": len(accepted_renames),
        "rejected_rename_count": len(rejected_renames),
        "renames": renames,
        "accepted_renames": accepted_renames,
        "rejected_renames": rejected_renames,
        "applied_renames": applied_renames,
        "summary": f"Applied {applied_count} structured rename(s).",
    }


def structured_language_repair_failure_history_record(
    *,
    iteration: int,
    stage: str,
    error: str,
) -> dict[str, Any]:
    return {
        "iteration": iteration,
        "batch_attempt": 1,
        "accepted": [],
        "rejected": [{"op": "STRUCTURED_LANGUAGE_REPAIR", "stage": stage, "error": error}],
        "focus": "Repair structured model names to match the specification language.",
        "feedback": error,
    }


def structured_language_repair_failure_event_payload(*, stage: str, error: str) -> dict[str, Any]:
    return {
        "agent_id": "structuredLanguageRepair",
        "stage": stage,
        "applied_count": 0,
        "error": error,
        "summary": f"Structured language repair failed: {error}",
    }


__all__ = [
    "structured_language_repair_delta_payload",
    "structured_language_repair_done_payload",
    "structured_language_repair_failure_event_payload",
    "structured_language_repair_failure_history_record",
    "structured_language_repair_prompt_payload",
    "structured_language_repair_start_payload",
    "structured_language_repair_success_event_payload",
    "structured_language_repair_success_history_record",
]
