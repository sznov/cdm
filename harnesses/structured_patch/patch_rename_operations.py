from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_normalization import (
    find_structured_entity_payload,
    normalize_structured_name,
    resolve_structured_entity_name,
    structured_entity_name_from_ref,
    structured_entity_names,
    structured_relationship_matches,
)
from core.schemas import StructuredOutputError


def apply_rename_patch_operation(
    payload: dict[str, Any],
    op_name: str,
    op: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    if op_name == "renameEntity":
        return _apply_rename_entity(payload, op, name_policy=name_policy)
    if op_name == "renameAttribute":
        return _apply_rename_attribute(payload, op, name_policy=name_policy)
    return _apply_rename_relationship(payload, op, name_policy=name_policy)


def _apply_rename_entity(
    payload: dict[str, Any],
    op: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    old = resolve_structured_entity_name(
        op.get("old") or op.get("entity"),
        payload,
        name_policy=name_policy,
    )
    new = normalize_structured_name(
        op.get("new") or op.get("new_name") or op.get("newName"),
        style="upper",
        name_policy=name_policy,
    )
    if not isinstance(new, str) or not new:
        raise StructuredOutputError("renameEntity requires a non-empty new name.")
    names = structured_entity_names(payload)
    old_exists = any(name_policy.names_equal(old, name) for name in names)
    new_exists = any(name_policy.names_equal(new, name) for name in names)
    if not old_exists and new_exists:
        return {"status": "already_satisfied", "op": op, "reason": "Entity already has the requested name."}
    if not old_exists:
        raise StructuredOutputError("renameEntity references a missing entity.")
    if name_policy.preserves_unicode and name_policy.names_equal(old, new):
        return {
            "status": "already_satisfied",
            "op": op,
            "reason": "Entity already has the requested normalized name.",
        }
    if new_exists:
        raise StructuredOutputError("renameEntity new name already exists.")
    for entity in payload["entities"]:
        if name_policy.names_equal(entity.get("name"), old):
            entity["name"] = new
        entity["inherits_from"] = [
            new if name_policy.names_equal(parent, old) else parent
            for parent in entity.get("inherits_from") or []
        ]
    for relationship in payload.get("relationships") or []:
        for end_name in ("source", "target"):
            end = relationship.get(end_name) if isinstance(relationship, dict) else None
            if isinstance(end, dict) and name_policy.names_equal(end.get("entity"), old):
                end["entity"] = new
    return None


def _apply_rename_attribute(
    payload: dict[str, Any],
    op: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    entity = find_structured_entity_payload(
        payload,
        op.get("entity") or op.get("entityName"),
        name_policy=name_policy,
    )
    if entity is None:
        raise StructuredOutputError("renameAttribute references a missing entity.")
    old = normalize_structured_name(
        op.get("old") or op.get("name") or op.get("attribute"),
        style="lower",
        name_policy=name_policy,
    )
    new = normalize_structured_name(
        op.get("new") or op.get("new_name") or op.get("newName"),
        style="lower",
        name_policy=name_policy,
    )
    attr_names = {attribute.get("name") for attribute in entity.get("attributes") or [] if isinstance(attribute, dict)}
    old_exists = any(name_policy.names_equal(old, name) for name in attr_names)
    new_exists = any(name_policy.names_equal(new, name) for name in attr_names)
    if not old_exists and new_exists:
        return {"status": "already_satisfied", "op": op, "reason": "Attribute already has the requested name."}
    if not old_exists:
        raise StructuredOutputError("renameAttribute references a missing attribute.")
    if name_policy.preserves_unicode and name_policy.names_equal(old, new):
        return {
            "status": "already_satisfied",
            "op": op,
            "reason": "Attribute already has the requested normalized name.",
        }
    if new_exists:
        raise StructuredOutputError("renameAttribute new name already exists.")
    for attribute in entity.get("attributes") or []:
        if isinstance(attribute, dict) and name_policy.names_equal(attribute.get("name"), old):
            attribute["name"] = new
    for part in entity.get("identifier") or []:
        if (
            isinstance(part, dict)
            and part.get("kind") == "attribute"
            and name_policy.names_equal(part.get("ref"), old)
        ):
            part["ref"] = new
    return None


def _apply_rename_relationship(
    payload: dict[str, Any],
    op: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    old = normalize_structured_name(
        op.get("old") or op.get("name") or op.get("relationship"),
        style="lower",
        name_policy=name_policy,
    )
    new = normalize_structured_name(
        op.get("new") or op.get("new_name") or op.get("newName"),
        style="lower",
        name_policy=name_policy,
    )
    source = (
        structured_entity_name_from_ref(op.get("source"), payload, name_policy=name_policy)
        if op.get("source")
        else None
    )
    target = (
        structured_entity_name_from_ref(op.get("target"), payload, name_policy=name_policy)
        if op.get("target")
        else None
    )
    if name_policy.preserves_unicode and name_policy.names_equal(old, new):
        existing = any(
            isinstance(relationship, dict)
            and structured_relationship_matches(
                relationship,
                name=old,
                source=source,
                target=target,
                name_policy=name_policy,
            )
            for relationship in payload.get("relationships") or []
        )
        if existing:
            return {
                "status": "already_satisfied",
                "op": op,
                "reason": "Relationship already has the requested normalized name.",
            }
    matched = 0
    for relationship in payload.get("relationships") or []:
        if isinstance(relationship, dict) and structured_relationship_matches(
            relationship,
            name=old,
            source=source,
            target=target,
            name_policy=name_policy,
        ):
            relationship["name"] = new
            matched += 1
    if matched == 0:
        existing_new = any(
            isinstance(relationship, dict)
            and structured_relationship_matches(
                relationship,
                name=new,
                source=source,
                target=target,
                name_policy=name_policy,
            )
            for relationship in payload.get("relationships") or []
        )
        if existing_new:
            return {"status": "already_satisfied", "op": op, "reason": "Relationship already has the requested name."}
        raise StructuredOutputError("renameRelationship references a missing relationship.")
    for entity in payload.get("entities") or []:
        for part in entity.get("identifier") or []:
            if (
                isinstance(part, dict)
                and part.get("kind") == "relationship"
                and name_policy.names_equal(part.get("ref"), old)
            ):
                part["ref"] = new
    return None


__all__ = ["apply_rename_patch_operation"]
