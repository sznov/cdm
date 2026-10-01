from __future__ import annotations

from typing import Any

from core.json_repair_reports import DETERMINISTIC_REPAIR_KIND
from harnesses.structured_patch.patch_parse_contract import (
    STRUCTURED_PATCH_SUPPORTED_OPS,
    canonical_structured_patch_op_name,
    structured_patch_operation_minimal_error,
)


def normalize_structured_model_issue_patch(raw_patch: Any) -> dict[str, Any] | None:
    if not isinstance(raw_patch, dict):
        return None
    patch = dict(raw_patch)
    patch["op"] = canonical_structured_patch_op_name(patch.get("op") or patch.get("operation") or patch.get("type"))
    if patch["op"] not in STRUCTURED_PATCH_SUPPORTED_OPS:
        return None
    if structured_patch_operation_minimal_error(patch):
        return None
    return patch


def parse_structured_model_issues_payload(raw_issues: Any) -> list[dict[str, Any]]:
    if raw_issues is None:
        return []
    if not isinstance(raw_issues, list):
        return []
    issues: list[dict[str, Any]] = []
    for index, item in enumerate(raw_issues, start=1):
        if not isinstance(item, dict):
            continue
        raw_kind = str(item.get("kind") or item.get("type") or "decision").strip()
        normalized_kind = raw_kind.lower().replace("_", "").replace("-", "")
        if normalized_kind in {"harderror", "error", "hard"}:
            kind = "hardError"
        elif normalized_kind in {"decision", "choice", "policydecision", "policychoice"}:
            kind = "decision"
        elif normalized_kind in {"assumption", "assumed", "assumptionmade"}:
            kind = "assumption"
        elif normalized_kind in {"deterministicrepair", "jsonrepair", "syntaxrepair", "repair"}:
            kind = DETERMINISTIC_REPAIR_KIND
        else:
            kind = "decision"
        raw_options = item.get("options") or []
        if isinstance(raw_options, dict):
            raw_options = [raw_options]
        if not isinstance(raw_options, list):
            raw_options = []
        if not raw_options and "patch" in item:
            raw_options = [{"label": str(item.get("label") or item.get("summary") or "Apply patch"), "patch": item.get("patch")}]
        options: list[dict[str, Any]] = []
        for option_index, option in enumerate(raw_options, start=1):
            if isinstance(option, str):
                option = {"label": option, "patch": None}
            if not isinstance(option, dict):
                continue
            patch = normalize_structured_model_issue_patch(option.get("patch"))
            options.append(
                {
                    "label": str(option.get("label") or option.get("title") or f"Option {option_index}").strip(),
                    "patch": patch,
                }
            )
        issues.append(
            {
                "id": str(item.get("id") or f"I{index}").strip() or f"I{index}",
                "kind": kind,
                "target": str(item.get("target") or item.get("artifact") or "").strip(),
                "summary": str(item.get("summary") or item.get("title") or "").strip(),
                "evidence": str(item.get("evidence") or "").strip(),
                "options": options,
            }
        )
    return issues


__all__ = [
    "normalize_structured_model_issue_patch",
    "parse_structured_model_issues_payload",
]
