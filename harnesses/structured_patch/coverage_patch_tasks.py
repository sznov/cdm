from __future__ import annotations

from typing import Any

from core.json_parsing import parse_json_object_output
from core.schemas import StructuredOutputError


def parse_critic_patch_tasks_output(raw_output: str, *, max_tasks: int = 8) -> list[dict[str, Any]]:
    payload = parse_json_object_output(raw_output, label="Critic patch task planner")
    raw_tasks = payload.get("tasks") or payload.get("patch_tasks") or payload.get("patchTasks") or []
    if raw_tasks is None:
        raw_tasks = []
    if not isinstance(raw_tasks, list):
        raise StructuredOutputError("Critic patch task planner output must contain a tasks list.")

    allowed_kinds = {
        "addEntity",
        "addRelationship",
        "addAttribute",
        "fixIdentifier",
        "fixInheritance",
        "rename",
        "removeUnsupported",
        "other",
    }
    tasks: list[dict[str, Any]] = []
    for index, item in enumerate(raw_tasks, start=1):
        if isinstance(item, str):
            item = {"summary": item}
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or item.get("suggested_change") or item.get("change") or "").strip()
        target = str(item.get("target") or item.get("concept") or item.get("artifact") or "").strip()
        if not summary and not target:
            continue
        kind = str(item.get("kind") or "other").strip() or "other"
        if kind not in allowed_kinds:
            kind = "other"
        allowed_scope = item.get("allowed_scope") or item.get("allowedScope") or []
        if isinstance(allowed_scope, str):
            allowed_scope = [part.strip() for part in allowed_scope.split(",") if part.strip()]
        if not isinstance(allowed_scope, list):
            allowed_scope = []
        tasks.append(
            {
                "id": f"PT{len(tasks) + 1}",
                "source_id": str(item.get("id") or f"PT{index}").strip() or f"PT{index}",
                "finding_id": str(item.get("finding_id") or item.get("findingId") or "").strip(),
                "kind": kind,
                "target": target,
                "summary": summary or target,
                "allowed_scope": [str(scope).strip() for scope in allowed_scope if str(scope).strip()],
                "evidence": str(item.get("evidence") or "").strip(),
            }
        )
        if len(tasks) >= max(1, int(max_tasks or 1)):
            break
    return tasks


__all__ = ["parse_critic_patch_tasks_output"]
