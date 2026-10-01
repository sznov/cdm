from __future__ import annotations

from typing import Any

from harnesses.structured_patch.decision_merge import merge_decision_patches
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)


def _decision_option_id_for_label(label: str, fallback: str) -> tuple[str, str]:
    normalized_label = label.lower()
    if normalized_label in {"keep", "keep as-is", "keep as is", "leave unchanged"} or normalized_label.startswith("keep "):
        return "keep", "keep as-is"
    if "something else" in normalized_label:
        return "custom", label
    return fallback, label


def decision_patches_from_structured_model_issues(
    issues: list[dict[str, Any]],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    for issue in issues or []:
        if issue.get("kind") not in {"decision", "assumption"}:
            continue
        issue_options = [option for option in issue.get("options") or [] if isinstance(option, dict)]
        operation_options = [option for option in issue_options if isinstance(option.get("patch"), dict)]
        if operation_options:
            option_count = len(operation_options)
            first_patch = operation_options[0]["patch"]
            decision_options: list[dict[str, Any]] = []
            for operation_index, option in enumerate(operation_options, start=1):
                patch = option.get("patch")
                option_id = "apply" if option_count == 1 else f"apply-{operation_index}"
                decision_options.append(
                    {
                        "id": option_id,
                        "label": str(option.get("label") or f"apply option {operation_index}").strip()
                        or f"apply option {operation_index}",
                        "operation": patch,
                    }
                )
            for option in issue_options:
                if isinstance(option.get("patch"), dict):
                    continue
                label = str(option.get("label") or option.get("title") or "").strip()
                if label:
                    option_id, label = _decision_option_id_for_label(label, f"note-{len(decision_options) + 1}")
                    decision_options.append({"id": option_id, "label": label, "operation": None})
            patches.append(
                {
                    "id": str(issue.get("id") or f"I{len(patches) + 1}").strip() or f"I{len(patches) + 1}",
                    "status": "pending",
                    "kind": "draftAssumption" if issue.get("kind") == "assumption" else "draftDecision",
                    "title": str(issue.get("summary") or operation_options[0].get("label") or "Draft decision").strip(),
                    "question": str(issue.get("summary") or operation_options[0].get("label") or "Choose a draft decision option.").strip(),
                    "reason": str(issue.get("summary") or "").strip(),
                    "evidence": str(issue.get("evidence") or "").strip(),
                    "operation": first_patch,
                    "options": decision_options,
                    "source": "draft_model_issue",
                }
            )
            continue
        if issue_options:
            decision_options = []
            for option_index, option in enumerate(issue_options, start=1):
                label = str(option.get("label") or option.get("title") or f"Option {option_index}").strip()
                option_id, label = _decision_option_id_for_label(label, f"note-{option_index}")
                decision_options.append({"id": option_id, "label": label, "operation": None})
            patches.append(
                {
                    "id": str(issue.get("id") or f"I{len(patches) + 1}").strip() or f"I{len(patches) + 1}",
                    "status": "noted",
                    "kind": "draftAssumption" if issue.get("kind") == "assumption" else "draftDecision",
                    "title": str(issue.get("summary") or "Surfaced modeling assumption").strip(),
                    "question": str(issue.get("summary") or "Review this surfaced modeling assumption.").strip(),
                    "reason": str(issue.get("summary") or "").strip(),
                    "evidence": str(issue.get("evidence") or "").strip(),
                    "operation": None,
                    "options": decision_options,
                    "source": "draft_model_issue",
                }
            )
            continue
        if not issue_options:
            patches.append(
                {
                    "id": str(issue.get("id") or f"I{len(patches) + 1}").strip() or f"I{len(patches) + 1}",
                    "status": "noted",
                    "kind": "draftAssumption" if issue.get("kind") == "assumption" else "draftDecision",
                    "title": str(issue.get("summary") or "Surfaced modeling assumption").strip(),
                    "question": str(issue.get("summary") or "Review this surfaced modeling assumption.").strip(),
                    "reason": str(issue.get("summary") or "").strip(),
                    "evidence": str(issue.get("evidence") or "").strip(),
                    "operation": None,
                    "source": "draft_model_issue",
                }
            )
    return merge_decision_patches(patches, name_policy=name_policy)


__all__ = ["decision_patches_from_structured_model_issues"]
