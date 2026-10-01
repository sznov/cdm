from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)

def repair_structured_model_identifier_payloads(
    repaired: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any]:
    relationship_endpoints_by_name: dict[str, tuple[str, set[str]]] = {}
    for relationship in repaired.get("relationships") or []:
        if not isinstance(relationship, dict):
            continue
        relationship_name = str(relationship.get("name") or "").strip()
        if not relationship_name:
            continue
        endpoints: set[str] = set()
        for end_name in ("source", "target"):
            end = relationship.get(end_name)
            if isinstance(end, dict) and end.get("entity"):
                endpoints.add(name_policy.comparison_key(end["entity"]))
        relationship_endpoints_by_name[name_policy.comparison_key(relationship_name)] = (
            relationship_name,
            endpoints,
        )

    inheritance_marker_fragments = (
        "kindof",
        "subtypeof",
        "typeof",
        "specializ",
        "specialis",
        "inherit",
        "extends",
        "generaliz",
        "generalis",
    )

    for entity in repaired.get("entities", []):
        if not isinstance(entity, dict):
            continue
        entity_name = str(entity.get("name") or "").strip()
        if not entity_name:
            continue
        attributes = entity.get("attributes")
        if not isinstance(attributes, list):
            continue
        attribute_names = {
            name_policy.comparison_key(attribute.get("name")):
            str(attribute.get("name") or "")
            for attribute in attributes
            if isinstance(attribute, dict)
        }
        parent_names = {
            name_policy.comparison_key(parent)
            for parent in entity.get("inherits_from") or []
        }
        if parent_names:
            entity["identifier"] = []
            continue
        identifier = entity.get("identifier") or []
        if not isinstance(identifier, list):
            continue
        repaired_identifier: list[dict[str, str]] = []
        for part in identifier:
            if not isinstance(part, dict):
                continue
            kind = str(part.get("kind") or "")
            ref = str(part.get("ref") or "")
            if kind == "attribute":
                ref_key = name_policy.comparison_key(ref)
                id_key = name_policy.comparison_key("id")
                if ref_key == id_key and id_key not in attribute_names:
                    attributes.insert(0, {"name": "id", "type": "int"})
                    attribute_names[id_key] = "id"
                if ref_key in attribute_names:
                    repaired_identifier.append(
                        {"kind": "attribute", "ref": attribute_names[ref_key]}
                    )
                continue
            if kind == "relationship":
                relationship_entry = relationship_endpoints_by_name.get(
                    name_policy.comparison_key(ref)
                )
                if relationship_entry is None:
                    continue
                canonical_ref, endpoints = relationship_entry
                if name_policy.comparison_key(entity_name) not in endpoints:
                    continue
                normalized_ref = "".join(char for char in ref.lower() if char.isalnum())
                is_inheritance_marker = any(fragment in normalized_ref for fragment in inheritance_marker_fragments)
                if is_inheritance_marker and parent_names and any(parent in endpoints for parent in parent_names):
                    continue
                repaired_identifier.append({"kind": "relationship", "ref": canonical_ref})
        if repaired_identifier:
            entity["identifier"] = repaired_identifier
        elif parent_names:
            entity["identifier"] = []
        else:
            if name_policy.comparison_key("id") not in attribute_names:
                attributes.insert(0, {"name": "id", "type": "int"})
            entity["identifier"] = [{"kind": "attribute", "ref": "id"}]
    return repaired


__all__ = ["repair_structured_model_identifier_payloads"]
