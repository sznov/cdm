from __future__ import annotations

from typing import Any

from core.naming import to_lower_camel_ascii, to_upper_camel_ascii
from core.schemas import StructuredModel, validate_structured_model_links


def apply_structured_language_renames(
    model: StructuredModel,
    renames: list[dict[str, str]],
) -> tuple[StructuredModel, list[dict[str, Any]]]:
    payload = model.model_dump(mode="json")
    applied: list[dict[str, Any]] = []
    entity_rename_map = {
        (rename.get("old") or "").strip(): to_upper_camel_ascii((rename.get("new") or "").strip(), fallback="")
        for rename in renames
        if (rename.get("kind") or "").strip() == "entity"
    }

    def entity_names() -> set[str]:
        return {str(entity.get("name") or "") for entity in payload["entities"]}

    for rename in renames:
        kind = (rename.get("kind") or "").strip()
        old = (rename.get("old") or "").strip()
        new_raw = (rename.get("new") or "").strip()
        if kind == "entity":
            new = to_upper_camel_ascii(new_raw, fallback="")
            if not old or not new or new == old:
                continue
            names = entity_names()
            if old not in names or new in names:
                applied.append({**rename, "applied": False, "reason": "Entity rename skipped because old name was missing or new name already exists."})
                continue
            for entity in payload["entities"]:
                if entity.get("name") == old:
                    entity["name"] = new
                entity["inherits_from"] = [new if parent == old else parent for parent in entity.get("inherits_from", [])]
            for relationship in payload["relationships"]:
                if relationship.get("source", {}).get("entity") == old:
                    relationship["source"]["entity"] = new
                if relationship.get("target", {}).get("entity") == old:
                    relationship["target"]["entity"] = new
            applied.append({**rename, "new": new, "applied": True})
        elif kind == "attribute":
            entity_name = (rename.get("entity") or "").strip()
            new = to_lower_camel_ascii(new_raw, fallback="")
            if not entity_name or not old or not new or new == old:
                continue
            entity = next((item for item in payload["entities"] if item.get("name") == entity_name), None)
            if entity is None and entity_rename_map.get(entity_name):
                entity = next((item for item in payload["entities"] if item.get("name") == entity_rename_map[entity_name]), None)
            if not entity:
                applied.append({**rename, "applied": False, "reason": "Attribute rename skipped because entity was missing."})
                continue
            attributes = entity.get("attributes", [])
            attr_names = {attribute.get("name") for attribute in attributes}
            if old not in attr_names or new in attr_names:
                applied.append({**rename, "applied": False, "reason": "Attribute rename skipped because old name was missing or new name already exists."})
                continue
            for attribute in attributes:
                if attribute.get("name") == old:
                    attribute["name"] = new
            for identifier_part in entity.get("identifier", []):
                if identifier_part.get("kind") == "attribute" and identifier_part.get("ref") == old:
                    identifier_part["ref"] = new
            applied.append({**rename, "new": new, "applied": True})
        elif kind == "relationship":
            new = to_lower_camel_ascii(new_raw, fallback="")
            if not old or not new or new == old:
                continue
            matching_indices = [
                index
                for index, relationship in enumerate(payload["relationships"])
                if relationship.get("name") == old
            ]
            if not matching_indices:
                applied.append({**rename, "applied": False, "reason": "Relationship rename skipped because old name was missing."})
                continue
            for index in matching_indices:
                payload["relationships"][index]["name"] = new
            for entity in payload["entities"]:
                for identifier_part in entity.get("identifier", []):
                    if identifier_part.get("kind") == "relationship" and identifier_part.get("ref") == old:
                        identifier_part["ref"] = new
            applied.append({**rename, "new": new, "applied": True, "match_count": len(matching_indices)})

    repaired = StructuredModel.model_validate(payload)
    validate_structured_model_links(repaired)
    return repaired, applied


__all__ = ["apply_structured_language_renames"]
