from __future__ import annotations

from typing import Any

from harnesses.structured_patch.patch_normalization import normalize_structured_multiplicity


def sanitize_structured_model_payload_shape(repaired: dict[str, Any]) -> dict[str, Any]:
    for key in list(repaired.keys()):
        if key not in {"entities", "relationships"}:
            repaired.pop(key, None)
    for entity in repaired.get("entities", []):
        if not isinstance(entity, dict):
            continue
        for key in list(entity.keys()):
            if key not in {"name", "attributes", "identifier", "inherits_from"}:
                entity.pop(key, None)
        attributes = entity.get("attributes")
        if attributes is None:
            attributes = []
            entity["attributes"] = attributes
        elif isinstance(attributes, dict):
            repaired_attributes: list[dict[str, str]] = []
            for name, raw_type in attributes.items():
                if not str(name or "").strip():
                    continue
                attr_type = str(raw_type or "string").strip()
                if attr_type not in {"string", "int", "real", "bool", "date"}:
                    attr_type = "string"
                repaired_attributes.append({"name": str(name).strip(), "type": attr_type})
            attributes = repaired_attributes
            entity["attributes"] = attributes
        if not isinstance(attributes, list):
            continue
        for attribute in attributes:
            if isinstance(attribute, dict):
                for key in list(attribute.keys()):
                    if key not in {"name", "type"}:
                        attribute.pop(key, None)
        attribute_names = {
            str(attribute.get("name") or "")
            for attribute in attributes
            if isinstance(attribute, dict)
        }
        identifier = entity.get("identifier") or []
        if not isinstance(identifier, list):
            continue
        repaired_identifier: list[Any] = []
        for part in identifier:
            if not isinstance(part, dict):
                repaired_identifier.append(part)
                continue
            part = {key: value for key, value in part.items() if key in {"kind", "ref", "name"}}
            kind = str(part.get("kind") or "")
            ref = str(part.get("ref") or "")
            if kind in {"attribute", "relationship"} and ref:
                repaired_identifier.append({"kind": kind, "ref": ref})
                continue
            if kind == "id" and not ref:
                repaired_identifier.append({"kind": "attribute", "ref": "id"})
                continue
            if ref and (kind == "id" or ref in attribute_names or ref == "id"):
                repaired_identifier.append({"kind": "attribute", "ref": ref})
                continue
            name = str(part.get("name") or "").strip()
            if name:
                repaired_identifier.append({"kind": "attribute", "ref": name})
            else:
                repaired_identifier.append(part)
        entity["identifier"] = repaired_identifier
        identifier = repaired_identifier
        raw_parents_for_identity = entity.get("inherits_from")
        has_parent_for_identity = isinstance(raw_parents_for_identity, list) and any(
            str(parent or "").strip() and str(parent or "").strip().lower() not in {"none", "null", "nil"}
            for parent in raw_parents_for_identity
        )
        if has_parent_for_identity:
            entity["identifier"] = []
        else:
            needs_surrogate_id = any(
                isinstance(part, dict)
                and str(part.get("kind") or "") == "attribute"
                and str(part.get("ref") or "") == "id"
                for part in identifier
            )
            if needs_surrogate_id and "id" not in attribute_names:
                attributes.insert(0, {"name": "id", "type": "int"})
        parents = entity.get("inherits_from")
        if isinstance(parents, list):
            repaired_parents: list[str] = []
            for parent in parents:
                parent_name = str(parent or "").strip()
                if not parent_name or parent_name.lower() in {"none", "null", "nil"}:
                    continue
                if parent_name not in repaired_parents:
                    repaired_parents.append(parent_name)
            entity["inherits_from"] = repaired_parents
    relationships = repaired.get("relationships")
    if relationships is None:
        repaired["relationships"] = []
    elif isinstance(relationships, list):
        repaired_relationships: list[Any] = []
        for relationship in relationships:
            if not isinstance(relationship, dict):
                continue
            for key in list(relationship.keys()):
                if key not in {"name", "source", "target"}:
                    relationship.pop(key, None)
            for end_name in ("source", "target"):
                end = relationship.get(end_name)
                if not isinstance(end, dict):
                    continue
                for key in list(end.keys()):
                    if key not in {"entity", "multiplicity", "role"}:
                        end.pop(key, None)
                if "multiplicity" in end:
                    end["multiplicity"] = normalize_structured_multiplicity(end.get("multiplicity"))
            source = relationship.get("source")
            target = relationship.get("target")
            if (
                isinstance(source, dict)
                and isinstance(target, dict)
                and str(source.get("entity") or "").strip()
                and str(target.get("entity") or "").strip()
            ):
                repaired_relationships.append(relationship)
        repaired["relationships"] = repaired_relationships
    return repaired


__all__ = ["sanitize_structured_model_payload_shape"]
