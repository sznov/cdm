from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_normalization import (
    normalize_structured_name,
    normalize_structured_relationship_payload,
    resolve_structured_entity_name,
    structured_entity_name_from_ref,
    structured_entity_names,
    structured_relationship_matches,
)


def apply_relationship_patch_operation(
    payload: dict[str, Any],
    op_name: str,
    op: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    if op_name == "addRelationship":
        relationship = normalize_structured_relationship_payload(op, name_policy=name_policy)
        for end_name in ("source", "target"):
            relationship[end_name]["entity"] = resolve_structured_entity_name(
                relationship[end_name].get("entity"),
                payload,
                name_policy=name_policy,
            )
        name_keys = {
            name_policy.comparison_key(name)
            for name in structured_entity_names(payload)
        }
        missing = [
            entity_name
            for entity_name in (relationship.get("source", {}).get("entity"), relationship.get("target", {}).get("entity"))
            if name_policy.comparison_key(entity_name) not in name_keys
        ]
        if missing:
            return {"status": "deferred", "op": op, "missing_entities": sorted(set(missing)), "reason": "Relationship endpoint entity is missing."}
        for existing in payload.get("relationships") or []:
            if not isinstance(existing, dict):
                continue
            if structured_relationship_matches(
                existing,
                name=relationship.get("name"),
                source=relationship["source"]["entity"],
                target=relationship["target"]["entity"],
                name_policy=name_policy,
            ):
                existing_source = existing.get("source") if isinstance(existing.get("source"), dict) else {}
                existing_target = existing.get("target") if isinstance(existing.get("target"), dict) else {}
                desired_source = relationship["source"]
                desired_target = relationship["target"]
                source_updates = {
                    key: desired_source[key]
                    for key in ("multiplicity", "role")
                    if key in desired_source and existing_source.get(key) != desired_source.get(key)
                }
                target_updates = {
                    key: desired_target[key]
                    for key in ("multiplicity", "role")
                    if key in desired_target and existing_target.get(key) != desired_target.get(key)
                }
                if not source_updates and not target_updates:
                    return {"status": "already_satisfied", "op": op, "reason": "Relationship already exists."}
                existing["source"] = {**existing_source, "entity": desired_source["entity"], **source_updates}
                existing["target"] = {**existing_target, "entity": desired_target["entity"], **target_updates}
                break
        else:
            payload.setdefault("relationships", []).append(relationship)
        return None

    name = (
        normalize_structured_name(
            op.get("name") or op.get("relationship"),
            style="lower",
            name_policy=name_policy,
        )
        if (op.get("name") or op.get("relationship"))
        else None
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
    kept_relationships = []
    removed_names: set[str] = set()
    for relationship in payload.get("relationships") or []:
        if isinstance(relationship, dict) and structured_relationship_matches(
            relationship,
            name=name,
            source=source,
            target=target,
            name_policy=name_policy,
        ):
            if relationship.get("name"):
                removed_names.add(str(relationship["name"]))
            continue
        kept_relationships.append(relationship)
    if len(kept_relationships) == len(payload.get("relationships") or []):
        return {"status": "already_satisfied", "op": op, "reason": "Relationship for removeRelationship is already absent."}
    payload["relationships"] = kept_relationships
    for entity in payload.get("entities") or []:
        if isinstance(entity, dict):
            entity["identifier"] = [
                part
                for part in entity.get("identifier") or []
                if not (
                    isinstance(part, dict)
                    and part.get("kind") == "relationship"
                    and any(name_policy.names_equal(part.get("ref"), removed_name) for removed_name in removed_names)
                )
            ]
    return None


__all__ = ["apply_relationship_patch_operation"]
