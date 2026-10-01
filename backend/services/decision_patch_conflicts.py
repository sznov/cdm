from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.services.decision_patch_options import decision_option_by_id, decision_option_operation
from harnesses.structured_patch.name_policy import StructuredNamePolicy


def decision_operation_identifier_conflict_key(
    operation: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy,
) -> str:
    if not isinstance(operation, dict):
        return ""
    if str(operation.get("op") or "").strip() != "setIdentifier":
        return ""
    entity = str(operation.get("entity") or "").strip()
    return f"identifier:{name_policy.comparison_key(entity)}" if entity else ""


def decision_choice_identifier_conflict_key(
    patch: dict[str, Any],
    option: dict[str, Any],
    operation: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy,
) -> str:
    return (
        decision_operation_identifier_conflict_key(operation, name_policy=name_policy)
        or decision_operation_identifier_conflict_key(
            patch.get("operation") if isinstance(patch.get("operation"), dict) else None,
            name_policy=name_policy,
        )
    )


def reject_conflicting_identifier_decision_choices(
    choices: list[dict[str, Any]],
    patch_by_id: dict[str, dict[str, Any]],
    *,
    name_policy: StructuredNamePolicy,
) -> None:
    seen: dict[str, str] = {}
    for choice in choices:
        patch_id = choice["patch_id"]
        patch = patch_by_id[patch_id]
        option = decision_option_by_id(
            patch,
            choice.get("option_id"),
            name_policy=name_policy,
        )
        operation = decision_option_operation(option)
        conflict_key = decision_choice_identifier_conflict_key(
            patch,
            option,
            operation,
            name_policy=name_policy,
        )
        if not conflict_key:
            continue
        previous_patch_id = seen.get(conflict_key)
        if previous_patch_id and previous_patch_id != patch_id:
            entity = conflict_key.split(":", 1)[1]
            raise HTTPException(
                status_code=400,
                detail=(
                    "Conflicting identifier decisions selected for "
                    f"{entity}. Choose one identifier decision and send it as a single selection."
                ),
            )
        seen[conflict_key] = patch_id


__all__ = [
    "decision_choice_identifier_conflict_key",
    "decision_operation_identifier_conflict_key",
    "reject_conflicting_identifier_decision_choices",
]
