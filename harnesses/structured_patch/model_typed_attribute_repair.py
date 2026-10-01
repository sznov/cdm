from __future__ import annotations

from copy import deepcopy
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.model_typed_attribute_targets import (
    entity_target_for_attribute_name,
    entity_target_for_attribute_type,
    relationship_base_name_for_entity_attribute,
    relationship_name_for_typed_attribute,
)
from harnesses.structured_patch.patch_normalization import (
    STRUCTURED_ATTRIBUTE_TYPE_ALIASES,
    STRUCTURED_ATTRIBUTE_TYPES,
)


def repair_structured_entity_typed_attributes_payload(
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
        repaired["relationships"] = relationships

    entity_names = {
        str(entity.get("name") or "")
        for entity in entities
        if isinstance(entity, dict) and str(entity.get("name") or "")
    }
    existing_relationship_names = {
        str(relationship.get("name") or "")
        for relationship in relationships
        if isinstance(relationship, dict) and str(relationship.get("name") or "")
    }
    existing_relationship_keys = {
        (
            name_policy.comparison_key(relationship.get("name")),
            name_policy.comparison_key((relationship.get("source") or {}).get("entity"))
            if isinstance(relationship.get("source"), dict)
            else "",
            name_policy.comparison_key((relationship.get("target") or {}).get("entity"))
            if isinstance(relationship.get("target"), dict)
            else "",
        )
        for relationship in relationships
        if isinstance(relationship, dict)
    }
    existing_relationship_by_endpoints: dict[tuple[str, str], str] = {}
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        source = relationship.get("source")
        target = relationship.get("target")
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        source_entity = str(source.get("entity") or "")
        target_entity = str(target.get("entity") or "")
        relationship_name = str(relationship.get("name") or "")
        if source_entity and target_entity and relationship_name:
            existing_relationship_by_endpoints.setdefault(
                (
                    name_policy.comparison_key(source_entity),
                    name_policy.comparison_key(target_entity),
                ),
                relationship_name,
            )

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_name = str(entity.get("name") or "")
        if not entity_name:
            continue
        attributes = entity.get("attributes")
        if not isinstance(attributes, list):
            continue

        kept_attributes: list[Any] = []
        attribute_relationship_refs: dict[str, str] = {}
        for attribute in attributes:
            if not isinstance(attribute, dict):
                kept_attributes.append(attribute)
                continue
            attribute_name = str(attribute.get("name") or "").strip()
            raw_type = attribute.get("type")
            target_entity = entity_target_for_attribute_type(
                raw_type,
                entity_names,
                name_policy=name_policy,
            )
            if (
                not target_entity
                and isinstance(raw_type, str)
                and raw_type.strip().lower() in STRUCTURED_ATTRIBUTE_TYPES
            ):
                target_entity = entity_target_for_attribute_name(
                    attribute_name,
                    entity_names,
                    source_entity_name=entity_name,
                    name_policy=name_policy,
                )
            if not attribute_name or not target_entity:
                if isinstance(raw_type, str):
                    normalized_type = STRUCTURED_ATTRIBUTE_TYPE_ALIASES.get(raw_type.strip().lower())
                    if normalized_type:
                        attribute["type"] = normalized_type
                kept_attributes.append(attribute)
                continue

            relationship_name = relationship_name_for_typed_attribute(
                base_name=relationship_base_name_for_entity_attribute(attribute_name),
                existing_relationship_names=existing_relationship_names,
                name_policy=name_policy,
            )
            relationship_key = (
                name_policy.comparison_key(relationship_name),
                name_policy.comparison_key(entity_name),
                name_policy.comparison_key(target_entity),
            )
            endpoint_key = (
                name_policy.comparison_key(entity_name),
                name_policy.comparison_key(target_entity),
            )
            existing_endpoint_relationship_name = existing_relationship_by_endpoints.get(endpoint_key)
            if existing_endpoint_relationship_name:
                relationship_name = existing_endpoint_relationship_name
            elif relationship_key not in existing_relationship_keys:
                relationships.append(
                    {
                        "name": relationship_name,
                        "source": {"entity": entity_name},
                        "target": {"entity": target_entity},
                    }
                )
                existing_relationship_names.add(relationship_name)
                existing_relationship_keys.add(relationship_key)
                existing_relationship_by_endpoints[endpoint_key] = relationship_name
            attribute_relationship_refs[name_policy.comparison_key(attribute_name)] = relationship_name

        entity["attributes"] = kept_attributes
        identifier = entity.get("identifier")
        if isinstance(identifier, list) and attribute_relationship_refs:
            for part in identifier:
                if (
                    isinstance(part, dict)
                    and part.get("kind") == "attribute"
                    and name_policy.comparison_key(part.get("ref")) in attribute_relationship_refs
                ):
                    part["kind"] = "relationship"
                    part["ref"] = attribute_relationship_refs[
                        name_policy.comparison_key(part.get("ref"))
                    ]

    return repaired


__all__ = [
    'relationship_name_for_typed_attribute',
    'entity_target_for_attribute_type',
    'entity_target_for_attribute_name',
    'relationship_base_name_for_entity_attribute',
    'repair_structured_entity_typed_attributes_payload'
]
