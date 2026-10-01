from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from harnesses.structured_patch.decision_options import (
    default_decision_patch_options,
    ensure_decision_patch_options,
)
from harnesses.structured_patch.name_policy import StructuredNamePolicy


def decision_patch_is_final(patch: dict[str, Any]) -> bool:
    return str(patch.get("status") or "").strip().lower() in {
        "applied",
        "rejected",
        "noted",
        "obsolete",
        "resolved",
    }


def decision_patch_requires_choice(patch: dict[str, Any]) -> bool:
    return isinstance(patch.get("operation"), dict) and not decision_patch_is_final(patch)


def decision_patch_sort_rank(patch: dict[str, Any]) -> int:
    if decision_patch_requires_choice(patch):
        return 0
    kind = str(patch.get("kind") or "").lower()
    status = str(patch.get("status") or "").lower()
    if "decision" in kind and status != "noted":
        return 1
    if "assumption" in kind and status != "noted":
        return 2
    if status == "noted":
        return 4
    return 3


def sorted_decision_patches(patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item[1]
        for item in sorted(
            enumerate(patches),
            key=lambda item: (decision_patch_sort_rank(item[1]), item[0]),
        )
    ]


def normalized_decision_patch_options_for_apply(
    patch: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy,
) -> list[dict[str, Any]]:
    normalized = dict(patch)
    ensure_decision_patch_options(normalized, name_policy=name_policy)
    options = normalized.get("options") if isinstance(normalized.get("options"), list) else []
    if not options and isinstance(normalized.get("operation"), dict):
        options = default_decision_patch_options(normalized, name_policy=name_policy)
    return [option for option in options if isinstance(option, dict)]


def decision_option_by_id(
    patch: dict[str, Any],
    option_id: str | None,
    *,
    name_policy: StructuredNamePolicy,
) -> dict[str, Any]:
    options = normalized_decision_patch_options_for_apply(
        patch,
        name_policy=name_policy,
    )
    normalized_id = str(option_id or "apply").strip() or "apply"
    for option in options:
        if str(option.get("id") or "").strip() == normalized_id:
            return option
    if normalized_id == "apply" and isinstance(patch.get("operation"), dict):
        return default_decision_patch_options(patch, name_policy=name_policy)[0]
    raise HTTPException(status_code=404, detail=f"Decision option not found: {patch.get('id')}.{normalized_id}")


def decision_option_operation(option: dict[str, Any]) -> dict[str, Any] | None:
    operation = option.get("operation")
    if not isinstance(operation, dict) and isinstance(option.get("patch"), dict):
        operation = option["patch"]
    return operation if isinstance(operation, dict) else None


def decision_selection_chat_message(selections: list[dict[str, Any]]) -> str:
    lines = ["Decision selections:"]
    for selection in selections:
        patch = selection.get("patch") if isinstance(selection.get("patch"), dict) else {}
        label = str(selection.get("label") or "").strip() or str(patch.get("title") or patch.get("id") or "decision").strip()
        custom_text = str(selection.get("custom_text") or "").strip()
        if custom_text:
            lines.append(f"- {label}: {custom_text}")
        else:
            lines.append(f"- {label}")
    return "\n".join(lines)


__all__ = [
    "decision_option_by_id",
    "decision_option_operation",
    "decision_patch_is_final",
    "decision_patch_requires_choice",
    "decision_patch_sort_rank",
    "decision_selection_chat_message",
    "normalized_decision_patch_options_for_apply",
    "sorted_decision_patches",
]
