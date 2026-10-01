from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_normalization import (
    find_structured_entity_payload,
    resolve_structured_entity_name,
    structured_entity_names,
)
from core.schemas import StructuredOutputError


def apply_inheritance_patch_operation(
    payload: dict[str, Any],
    op_name: str,
    op: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    entity = find_structured_entity_payload(
        payload,
        op.get("entity") or op.get("child") or op.get("subtype"),
        name_policy=name_policy,
    )
    parent_name = resolve_structured_entity_name(
        op.get("parent") or op.get("parent_entity") or op.get("parentEntity"),
        payload,
        name_policy=name_policy,
    )
    if entity is None:
        raise StructuredOutputError(f"{op_name} references a missing child entity.")
    if not any(name_policy.names_equal(parent_name, name) for name in structured_entity_names(payload)):
        raise StructuredOutputError(f"{op_name} references a missing parent entity.")
    parents = entity.setdefault("inherits_from", [])
    if op_name == "addInheritance":
        if any(name_policy.names_equal(parent_name, parent) for parent in parents):
            return {"status": "already_satisfied", "op": op, "reason": "Inheritance already exists."}
        parents.append(parent_name)
        return None
    if not any(name_policy.names_equal(parent_name, parent) for parent in parents):
        return {"status": "already_satisfied", "op": op, "reason": "Inheritance is already absent."}
    entity["inherits_from"] = [
        parent
        for parent in parents
        if not name_policy.names_equal(parent, parent_name)
    ]
    return None


__all__ = ["apply_inheritance_patch_operation"]
