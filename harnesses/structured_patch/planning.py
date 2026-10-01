from __future__ import annotations

import json
from typing import Any

from core.json_parsing import extract_json_object, reject_duplicate_json_keys
from core.schemas import StructuredOutputError


def normalize_modeling_plan_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        payload = {
            "phases": [
                {
                    "id": "P1",
                    "name": "Modeling tasks",
                    "goal": "Satisfy extracted modeling obligations.",
                    "tasks": payload,
                }
            ],
            "open_questions": [],
        }
    if not isinstance(payload, dict):
        raise StructuredOutputError("Modeling plan must be a JSON object.")

    raw_phases = payload.get("phases")
    if raw_phases is None and isinstance(payload.get("tasks"), list):
        raw_phases = [
            {
                "id": "P1",
                "name": "Modeling tasks",
                "goal": "Satisfy extracted modeling obligations.",
                "tasks": payload.get("tasks"),
            }
        ]
    if not isinstance(raw_phases, list) or not raw_phases:
        raise StructuredOutputError("Modeling plan must contain a non-empty phases list.")

    phases: list[dict[str, Any]] = []
    task_counter = 1
    for phase_index, raw_phase in enumerate(raw_phases, start=1):
        if not isinstance(raw_phase, dict):
            continue
        raw_tasks = raw_phase.get("tasks")
        if not isinstance(raw_tasks, list):
            raw_tasks = []
        tasks: list[dict[str, Any]] = []
        for raw_task in raw_tasks:
            if not isinstance(raw_task, dict):
                continue
            task = {
                "id": str(raw_task.get("id") or f"T{task_counter}"),
                "kind": str(raw_task.get("kind") or "entity"),
                "concept": str(raw_task.get("concept") or raw_task.get("name") or ""),
                "participants": raw_task.get("participants") if isinstance(raw_task.get("participants"), list) else [],
                "evidence": str(raw_task.get("evidence") or ""),
                "note": str(raw_task.get("note") or ""),
            }
            tasks.append(task)
            task_counter += 1
        phases.append(
            {
                "id": str(raw_phase.get("id") or f"P{phase_index}"),
                "name": str(raw_phase.get("name") or f"Phase {phase_index}"),
                "goal": str(raw_phase.get("goal") or ""),
                "tasks": tasks,
            }
        )

    open_questions = []
    for question in payload.get("open_questions") or payload.get("openQuestions") or []:
        if isinstance(question, dict):
            open_questions.append(
                {
                    "topic": str(question.get("topic") or ""),
                    "question": str(question.get("question") or ""),
                    "evidence": str(question.get("evidence") or ""),
                }
            )

    normalized = {"phases": phases, "open_questions": open_questions}
    if plan_task_count(normalized) <= 0:
        raise StructuredOutputError("Modeling plan must contain at least one task.")
    return normalized


def parse_modeling_plan_output(raw_output: str) -> dict[str, Any]:
    try:
        payload = json.loads(extract_json_object(raw_output), object_pairs_hook=reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(f"Modeling plan JSON parsing failed. {exc.msg} at line {exc.lineno} column {exc.colno}.") from exc
    return normalize_modeling_plan_payload(payload)


def plan_task_count(plan: dict[str, Any]) -> int:
    return sum(len(phase.get("tasks") or []) for phase in plan.get("phases") or [] if isinstance(phase, dict))


__all__ = [
    "normalize_modeling_plan_payload",
    "parse_modeling_plan_output",
    "plan_task_count",
]
