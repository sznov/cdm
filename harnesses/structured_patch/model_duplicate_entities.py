from __future__ import annotations

from copy import deepcopy
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
    StructuredNamePolicyError,
)


def coerce_attribute_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        repaired_attributes: list[dict[str, str]] = []
        for name, raw_type in value.items():
            if not str(name or "").strip():
                continue
            attr_type = str(raw_type or "string").strip()
            if attr_type not in {"string", "int", "real", "bool", "date"}:
                attr_type = "string"
            repaired_attributes.append({"name": str(name).strip(), "type": attr_type})
        return repaired_attributes
    return []


def repair_structured_duplicate_entities_payload(
    payload: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any]:
    repaired = deepcopy(payload)
    entities = repaired.get("entities")
    if not isinstance(entities, list):
        return repaired

    merged_entities: list[dict[str, Any]] = []
    by_name: dict[str, dict[str, Any]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        name = str(entity.get("name") or "").strip()
        if not name:
            continue
        name_key = name_policy.comparison_key(name)
        if name_key not in by_name:
            entity_copy = deepcopy(entity)
            if entity_copy.get("attributes") is None:
                entity_copy["attributes"] = []
            if not isinstance(entity_copy.get("identifier"), list):
                entity_copy["identifier"] = []
            if not isinstance(entity_copy.get("inherits_from"), list):
                entity_copy["inherits_from"] = []
            by_name[name_key] = entity_copy
            merged_entities.append(entity_copy)
            continue

        existing = by_name[name_key]
        existing_name = str(existing.get("name") or "")
        if existing_name != name:
            raise StructuredNamePolicyError(
                f"Entity names {existing_name!r} and {name!r} collide after NFKC case-folding."
            )
        existing_attributes = coerce_attribute_list(existing.get("attributes"))
        existing["attributes"] = existing_attributes
        existing_attribute_names = {
            name_policy.comparison_key(attribute.get("name")):
            str(attribute.get("name") or "")
            for attribute in existing_attributes
            if isinstance(attribute, dict)
        }
        for attribute in coerce_attribute_list(entity.get("attributes")):
            if not isinstance(attribute, dict):
                continue
            attribute_name = str(attribute.get("name") or "")
            attribute_key = name_policy.comparison_key(attribute_name)
            prior_attribute_name = existing_attribute_names.get(attribute_key)
            if prior_attribute_name is not None and prior_attribute_name != attribute_name:
                raise StructuredNamePolicyError(
                    f"Attribute names {prior_attribute_name!r} and {attribute_name!r} collide on "
                    f"entity {name!r} after NFKC case-folding."
                )
            if attribute_name and prior_attribute_name is None:
                existing_attributes.append(deepcopy(attribute))
                existing_attribute_names[attribute_key] = attribute_name

        existing_identifier = existing.setdefault("identifier", [])
        existing_identifier_keys = {
            (
                str(part.get("kind") or ""),
                name_policy.comparison_key(part.get("ref")),
            )
            for part in existing_identifier
            if isinstance(part, dict)
        }
        for part in entity.get("identifier") or []:
            if not isinstance(part, dict):
                continue
            key = (
                str(part.get("kind") or ""),
                name_policy.comparison_key(part.get("ref")),
            )
            if key[0] and key[1] and key not in existing_identifier_keys:
                existing_identifier.append(deepcopy(part))
                existing_identifier_keys.add(key)

        existing_parents = existing.setdefault("inherits_from", [])
        existing_parent_set = {
            name_policy.comparison_key(parent)
            for parent in existing_parents
        }
        for parent in entity.get("inherits_from") or []:
            parent_name = str(parent or "").strip()
            if not parent_name or parent_name.lower() in {"none", "null", "nil"}:
                continue
            parent_key = name_policy.comparison_key(parent_name)
            if parent_key not in existing_parent_set:
                existing_parents.append(parent)
                existing_parent_set.add(parent_key)

    repaired["entities"] = merged_entities
    return repaired


__all__ = ["coerce_attribute_list", "repair_structured_duplicate_entities_payload"]
