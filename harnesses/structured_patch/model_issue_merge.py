from __future__ import annotations

from typing import Any


def merge_structured_model_issue_lists(*issue_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for issue_list in issue_lists:
        for issue in issue_list or []:
            key = (
                str(issue.get("kind") or ""),
                str(issue.get("target") or ""),
                str(issue.get("summary") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(issue)
    return merged


__all__ = ["merge_structured_model_issue_lists"]
