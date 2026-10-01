from __future__ import annotations

import json
from typing import Any


def findings_from_structured_model_issues(issues: list[dict[str, Any]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for index, issue in enumerate(issues or [], start=1):
        if issue.get("kind") != "hardError":
            continue
        suggested_change = ""
        for option in issue.get("options") or []:
            if isinstance(option, dict) and isinstance(option.get("patch"), dict):
                suggested_change = json.dumps(option["patch"], ensure_ascii=False)
                break
        if not suggested_change:
            suggested_change = str(issue.get("summary") or "").strip()
        findings.append(
            {
                "id": f"DI{index}",
                "severity": "high",
                "kind": "other",
                "plan_task_id": "",
                "summary": str(issue.get("summary") or "Draft model reported a hard issue.").strip(),
                "evidence": str(issue.get("evidence") or "").strip(),
                "suggested_change": suggested_change,
            }
        )
    return findings


__all__ = ["findings_from_structured_model_issues"]
