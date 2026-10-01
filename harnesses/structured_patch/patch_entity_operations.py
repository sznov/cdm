from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_normalization import (
    normalize_structured_attributes_payload,
    normalize_structured_identifier_parts,
    normalize_structured_name,
    resolve_structured_entity_name,
    structured_entity_names,
)
from core.schemas import StructuredOutputError


def apply_entity_patch_operation(
    payload: dict[str, Any],
    op_name: str,
    op: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    if op_name == "addEntity":
        name = normalize_structured_name(
            op.get("name") or op.get("entity"),
            style="upper",
            name_policy=name_policy,
        )
        if not isinstance(name, str) or not name:
            raise StructuredOutputError("addEntity requires a non-empty name.")
        if any(name_policy.names_equal(name, existing) for existing in structured_entity_names(payload)):
            return {"status": "already_satisfied", "op": op, "reason": f"Entity '{name}' already exists."}
        raw_parents = op.get("inherits_from") or op.get("inheritsFrom") or []
        if isinstance(raw_parents, str):
            raw_parents = [raw_parents]
        parents = [
            resolve_structured_entity_name(parent, payload, name_policy=name_policy)
            for parent in raw_parents
            if str(parent or "").strip()
        ]
        identifier = normalize_structured_identifier_parts(
            op.get("identifier") or op.get("parts"),
            name_policy=name_policy,
        )
        payload["entities"].append(
            {
                "name": name,
                "attributes": normalize_structured_attributes_payload(
                    op.get("attributes"),
                    name_policy=name_policy,
                ),
                "identifier": identifier,
                "inherits_from": parents,
            }
        )
        return None

    name = resolve_structured_entity_name(
        op.get("name") or op.get("entity"),
        payload,
        name_policy=name_policy,
    )
    if not any(name_policy.names_equal(name, existing) for existing in structured_entity_names(payload)):
        return {"status": "already_satisfied", "op": op, "reason": "Entity for removeEntity is already absent."}
    blocking_children = [
        str(entity.get("name") or "")
        for entity in payload.get("entities") or []
        if isinstance(entity, dict)
        and any(name_policy.names_equal(name, parent) for parent in (entity.get("inherits_from") or []))
    ]
    blocking_relationships = [
        str(relationship.get("name") or "")
        for relationship in payload.get("relationships") or []
        if isinstance(relationship, dict)
        and (
            (
                isinstance(relationship.get("source"), dict)
                and name_policy.names_equal(relationship["source"].get("entity"), name)
            )
            or (
                isinstance(relationship.get("target"), dict)
                and name_policy.names_equal(relationship["target"].get("entity"), name)
            )
        )
    ]
    if blocking_children or blocking_relationships:
        blockers = []
        if blocking_children:
            blockers.append(f"child entities: {', '.join(sorted(set(blocking_children)))}")
        if blocking_relationships:
            blockers.append(f"relationships: {', '.join(sorted(set(blocking_relationships)))}")
        return {
            "status": "deferred",
            "op": op,
            "blocking_children": sorted(set(blocking_children)),
            "blocking_relationships": sorted(set(blocking_relationships)),
            "reason": "Entity still has references that must be removed first: " + "; ".join(blockers) + ".",
        }
    payload["entities"] = [
        entity
        for entity in payload.get("entities") or []
        if not (isinstance(entity, dict) and name_policy.names_equal(entity.get("name"), name))
    ]
    return None


__all__ = ["apply_entity_patch_operation"]
