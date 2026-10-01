from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_normalization import (
    find_structured_entity_payload,
    normalize_structured_attribute_type,
    normalize_structured_name,
)
from core.schemas import StructuredOutputError


def apply_attribute_patch_operation(
    payload: dict[str, Any],
    op_name: str,
    op: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    if op_name == "addAttribute":
        entity = find_structured_entity_payload(
            payload,
            op.get("entity") or op.get("entityName"),
            name_policy=name_policy,
        )
        if entity is None:
            raise StructuredOutputError("addAttribute references a missing entity.")
        name = normalize_structured_name(
            op.get("name") or op.get("attribute"),
            style="lower",
            name_policy=name_policy,
        )
        if not isinstance(name, str) or not name:
            raise StructuredOutputError("addAttribute requires a non-empty name.")
        attr_type = normalize_structured_attribute_type(op.get("type"))
        for attribute in entity.get("attributes") or []:
            if isinstance(attribute, dict) and name_policy.names_equal(attribute.get("name"), name):
                if attribute.get("type") == attr_type:
                    return {"status": "already_satisfied", "op": op, "reason": f"Attribute '{entity['name']}.{name}' already exists."}
                raise StructuredOutputError(f"Attribute '{entity['name']}.{name}' already exists with a different type.")
        entity.setdefault("attributes", []).append({"name": name, "type": attr_type})
        return None

    entity = find_structured_entity_payload(
        payload,
        op.get("entity") or op.get("entityName"),
        name_policy=name_policy,
    )
    if entity is None:
        return {"status": "already_satisfied", "op": op, "reason": "Entity for removeAttribute is already absent."}
    name = normalize_structured_name(
        op.get("name") or op.get("attribute"),
        style="lower",
        name_policy=name_policy,
    )
    before_count = len(entity.get("attributes") or [])
    entity["attributes"] = [
        attribute
        for attribute in entity.get("attributes") or []
        if not (isinstance(attribute, dict) and name_policy.names_equal(attribute.get("name"), name))
    ]
    entity["identifier"] = [
        part
        for part in entity.get("identifier") or []
        if not (
            isinstance(part, dict)
            and part.get("kind") == "attribute"
            and name_policy.names_equal(part.get("ref"), name)
        )
    ]
    if len(entity["attributes"]) == before_count:
        return {"status": "already_satisfied", "op": op, "reason": "Attribute for removeAttribute is already absent."}
    return None


__all__ = ["apply_attribute_patch_operation"]
