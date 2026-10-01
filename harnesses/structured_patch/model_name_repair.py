from __future__ import annotations

from copy import deepcopy
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
    StructuredNamePolicyError,
)
from harnesses.structured_patch.patch_normalization import normalize_structured_name


def _record_canonical_name(
    canonical_names: dict[str, str],
    value: str,
    *,
    kind: str,
    name_policy: StructuredNamePolicy,
) -> None:
    key = name_policy.comparison_key(value)
    existing = canonical_names.get(key)
    if existing is not None and existing != value:
        raise StructuredNamePolicyError(
            f"{kind} names {existing!r} and {value!r} collide after NFKC case-folding."
        )
    canonical_names[key] = value


def _repair_inheritance_references(
    entity: dict[str, Any],
    *,
    entity_name_map: dict[str, str],
    name_policy: StructuredNamePolicy,
) -> None:
    inherits_from = entity.get("inherits_from")
    if not isinstance(inherits_from, list):
        return
    normalized_parents: list[str] = []
    for parent in inherits_from:
        normalized_parent = entity_name_map.get(name_policy.comparison_key(parent))
        if normalized_parent is None:
            normalized_parent = normalize_structured_name(
                parent,
                style="upper",
                name_policy=name_policy,
            )
        if not isinstance(normalized_parent, str) or not normalized_parent:
            continue
        if name_policy.names_equal(normalized_parent, entity.get("name")):
            continue
        if not any(
            name_policy.names_equal(normalized_parent, existing)
            for existing in normalized_parents
        ):
            normalized_parents.append(normalized_parent)
    entity["inherits_from"] = normalized_parents


def repair_structured_model_names_payload(
    payload: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any]:
    repaired = deepcopy(payload)
    entities = repaired.get("entities")
    relationships = repaired.get("relationships")
    if not isinstance(entities, list):
        return repaired
    if not isinstance(relationships, list):
        relationships = []

    entity_name_map: dict[str, str] = {}
    canonical_entity_names: dict[str, str] = {}
    attribute_name_maps: dict[str, dict[str, str]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        old_entity_name = str(entity.get("name") or "")
        new_entity_name = normalize_structured_name(
            old_entity_name,
            style="upper",
            name_policy=name_policy,
        )
        if isinstance(new_entity_name, str) and new_entity_name:
            _record_canonical_name(
                canonical_entity_names,
                new_entity_name,
                kind="Entity",
                name_policy=name_policy,
            )
            entity["name"] = new_entity_name
            entity_name_map[name_policy.comparison_key(old_entity_name)] = new_entity_name
            entity_name_map[name_policy.comparison_key(new_entity_name)] = new_entity_name
        attributes = entity.get("attributes")
        if name_policy.preserves_unicode and isinstance(attributes, dict):
            attributes = [
                {"name": name, "type": raw_type}
                for name, raw_type in attributes.items()
            ]
            entity["attributes"] = attributes
        attribute_map: dict[str, str] = {}
        canonical_attribute_names: dict[str, str] = {}
        if isinstance(attributes, list):
            for attribute in attributes:
                if not isinstance(attribute, dict):
                    continue
                old_attribute_name = str(attribute.get("name") or "")
                new_attribute_name = normalize_structured_name(
                    old_attribute_name,
                    style="lower",
                    name_policy=name_policy,
                )
                if isinstance(new_attribute_name, str) and new_attribute_name:
                    _record_canonical_name(
                        canonical_attribute_names,
                        new_attribute_name,
                        kind=f"Attribute on {new_entity_name!r}",
                        name_policy=name_policy,
                    )
                    attribute["name"] = new_attribute_name
                    attribute_map[name_policy.comparison_key(old_attribute_name)] = new_attribute_name
                    attribute_map[name_policy.comparison_key(new_attribute_name)] = new_attribute_name
        if isinstance(new_entity_name, str) and new_entity_name:
            attribute_name_maps[name_policy.comparison_key(new_entity_name)] = attribute_map
        # Preserve the legacy order-sensitive path exactly. The refined policy
        # resolves inheritance only after the complete canonical map exists.
        if not name_policy.preserves_unicode:
            _repair_inheritance_references(
                entity,
                entity_name_map=entity_name_map,
                name_policy=name_policy,
            )

    if name_policy.preserves_unicode:
        for entity in entities:
            if isinstance(entity, dict):
                _repair_inheritance_references(
                    entity,
                    entity_name_map=entity_name_map,
                    name_policy=name_policy,
                )

    relationship_name_map: dict[str, str] = {}
    canonical_relationship_names: dict[str, str] = {}
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        old_relationship_name = relationship.get("name")
        if old_relationship_name:
            new_relationship_name = normalize_structured_name(
                old_relationship_name,
                style="lower",
                name_policy=name_policy,
            )
            if isinstance(new_relationship_name, str) and new_relationship_name:
                _record_canonical_name(
                    canonical_relationship_names,
                    new_relationship_name,
                    kind="Relationship",
                    name_policy=name_policy,
                )
            relationship["name"] = new_relationship_name
            relationship_name_map[name_policy.comparison_key(old_relationship_name)] = str(new_relationship_name)
            relationship_name_map[name_policy.comparison_key(new_relationship_name)] = str(new_relationship_name)
        for end_key in ("source", "target"):
            end = relationship.get(end_key)
            if not isinstance(end, dict):
                continue
            old_end_entity = str(end.get("entity") or "")
            if old_end_entity:
                resolved_entity = entity_name_map.get(name_policy.comparison_key(old_end_entity))
                end["entity"] = resolved_entity or normalize_structured_name(
                    old_end_entity,
                    style="upper",
                    name_policy=name_policy,
                )
            if end.get("role"):
                end["role"] = normalize_structured_name(
                    end.get("role"),
                    style="lower",
                    name_policy=name_policy,
                )

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_name = str(entity.get("name") or "")
        attribute_map = attribute_name_maps.get(name_policy.comparison_key(entity_name), {})
        identifier = entity.get("identifier")
        if not isinstance(identifier, list):
            continue
        for part in identifier:
            if not isinstance(part, dict):
                continue
            ref = str(part.get("ref") or "")
            if not ref:
                continue
            if part.get("kind") == "attribute":
                part["ref"] = attribute_map.get(
                    name_policy.comparison_key(ref),
                    normalize_structured_name(ref, style="lower", name_policy=name_policy),
                )
            elif part.get("kind") == "relationship":
                part["ref"] = relationship_name_map.get(
                    name_policy.comparison_key(ref),
                    normalize_structured_name(ref, style="lower", name_policy=name_policy),
                )

    return repaired


__all__ = [
    'repair_structured_model_names_payload'
]
