from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.decision_signatures import decision_patch_operation_label


def default_decision_patch_options(
    patch: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    operation = patch.get("operation") if isinstance(patch, dict) else None
    if not isinstance(operation, dict):
        return []
    apply_label = str(patch.get("apply_label") or "").strip() or decision_patch_operation_label(
        operation,
        name_policy=name_policy,
    )
    return [
        {"id": "apply", "label": apply_label, "operation": operation},
        {"id": "keep", "label": "keep as-is", "operation": None},
        {"id": "custom", "label": "something else", "operation": None, "requires_text": True},
    ]


def ensure_decision_patch_options(
    patch: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any]:
    operation = patch.get("operation") if isinstance(patch, dict) else None
    if not isinstance(operation, dict):
        return patch
    raw_options = patch.get("options")
    options = [dict(option) for option in raw_options if isinstance(option, dict)] if isinstance(raw_options, list) else []
    normalized: list[dict[str, Any]] = []
    has_operation_option = False
    has_keep_option = False
    has_custom_option = False
    operation_option_total = sum(
        1
        for option in options
        if isinstance(option.get("operation"), dict) or isinstance(option.get("patch"), dict)
    )
    operation_option_count = 0
    for index, option in enumerate(options, start=1):
        option_operation = option.get("operation")
        if option_operation is None and isinstance(option.get("patch"), dict):
            option_operation = option["patch"]
        option_has_operation = isinstance(option_operation, dict)
        if option_has_operation:
            operation_option_count += 1
        option_id = str(option.get("id") or option.get("option_id") or "").strip()
        if not option_id:
            option_id = (
                "apply"
                if option_has_operation and operation_option_total == 1
                else f"apply-{operation_option_count}"
                if option_has_operation
                else f"option-{index}"
            )
        label = str(option.get("label") or option.get("title") or option_id).strip() or option_id
        normalized_option = {
            **option,
            "id": option_id,
            "label": label,
            "operation": option_operation if option_has_operation else None,
        }
        normalized.append(normalized_option)
        if option_has_operation:
            has_operation_option = True
        normalized_id = option_id.lower()
        normalized_label = label.lower()
        if normalized_id == "keep" or normalized_label in {"keep", "keep as-is", "keep as is"} or normalized_label.startswith("keep "):
            has_keep_option = True
            normalized_option["id"] = "keep"
            normalized_option["label"] = "keep as-is"
        if normalized_id in {"custom", "other", "something_else", "something-else"} or "something else" in normalized_label:
            has_custom_option = True
            normalized_option["requires_text"] = True
    if not has_operation_option:
        normalized.insert(0, default_decision_patch_options(patch, name_policy=name_policy)[0])
    if not has_keep_option:
        normalized.append({"id": "keep", "label": "keep as-is", "operation": None})
    if not has_custom_option:
        normalized.append({"id": "custom", "label": "something else", "operation": None, "requires_text": True})
    patch["options"] = normalized
    return patch


__all__ = [
    "default_decision_patch_options",
    "ensure_decision_patch_options",
]
