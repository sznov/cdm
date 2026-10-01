from __future__ import annotations

from copy import deepcopy
from typing import Any

from harnesses.structured_patch.patch_model_lookup import structured_model_from_payload
from harnesses.structured_patch.patch_scalar_normalization import normalize_structured_multiplicity
from core.schemas import StructuredModel


def validate_structured_patch_payload(payload: dict[str, Any]) -> StructuredModel:
    return structured_model_from_payload(deepcopy(payload))


def remove_unused_fallback_id_attributes(payload: dict[str, Any]) -> None:
    for entity in payload.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        identifier = entity.get("identifier") or []
        if not isinstance(identifier, list) or not identifier:
            continue
        uses_id_as_identifier = any(
            isinstance(part, dict)
            and str(part.get("kind") or "") == "attribute"
            and str(part.get("ref") or "") == "id"
            for part in identifier
        )
        if uses_id_as_identifier:
            continue
        attributes = entity.get("attributes") or []
        if not isinstance(attributes, list):
            continue
        entity["attributes"] = [
            attribute
            for attribute in attributes
            if not (
                isinstance(attribute, dict)
                and str(attribute.get("name") or "") == "id"
                and str(attribute.get("type") or "int") == "int"
            )
        ]


def repair_relationship_identified_association_multiplicities_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Repair high-confidence association/context entity endpoint multiplicities.

    In this IR, multiplicity is written beside the endpoint entity and means how
    many instances of that endpoint can be associated with one instance of the
    opposite endpoint. If an entity is identified by multiple relationships and
    has facts of its own, each identifying parent/context normally sees many
    such fact rows. A 1/1 endpoint on the contextual entity would collapse the
    association into a global singleton per parent and cannot represent normal
    line-item, stock, assignment, allocation, or membership-style facts.
    """
    if not isinstance(payload, dict):
        return []
    entities = payload.get("entities")
    relationships = payload.get("relationships")
    if not isinstance(entities, list) or not isinstance(relationships, list):
        return []

    relationships_by_name: dict[str, dict[str, Any]] = {}
    duplicate_relationship_names: set[str] = set()
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        name = str(relationship.get("name") or "").strip()
        if not name:
            continue
        if name in relationships_by_name:
            duplicate_relationship_names.add(name)
            continue
        relationships_by_name[name] = relationship

    repairs: list[dict[str, Any]] = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_name = str(entity.get("name") or "").strip()
        if not entity_name:
            continue
        identifier = entity.get("identifier") or []
        if not isinstance(identifier, list):
            continue
        identifying_relationship_refs = []
        for part in identifier:
            if not isinstance(part, dict) or str(part.get("kind") or "") != "relationship":
                continue
            ref = str(part.get("ref") or "").strip()
            if ref and ref not in identifying_relationship_refs and ref not in duplicate_relationship_names:
                identifying_relationship_refs.append(ref)
        if len(identifying_relationship_refs) < 2:
            continue

        attributes = entity.get("attributes") or []
        has_own_fact = any(
            isinstance(attribute, dict) and str(attribute.get("name") or "").strip() not in {"", "id"}
            for attribute in attributes
        )
        if not has_own_fact:
            continue

        for relationship_name in identifying_relationship_refs:
            relationship = relationships_by_name.get(relationship_name)
            if not isinstance(relationship, dict):
                continue
            for end_name in ("source", "target"):
                end = relationship.get(end_name)
                if not isinstance(end, dict) or str(end.get("entity") or "").strip() != entity_name:
                    continue
                current_multiplicity = normalize_structured_multiplicity(end.get("multiplicity"))
                if current_multiplicity not in {"1", "0..1"}:
                    continue
                end["multiplicity"] = "0..*"
                repairs.append(
                    {
                        "kind": "deterministic_repair",
                        "check_id": "relationship_identified_association_multiplicity",
                        "entity": entity_name,
                        "relationship": relationship_name,
                        "endpoint": end_name,
                        "from": current_multiplicity,
                        "to": "0..*",
                        "summary": (
                            f"Set {entity_name} endpoint multiplicity on {relationship_name} to 0..* "
                            "because the entity is identified by multiple relationships and carries its own facts."
                        ),
                    }
                )
    return repairs


__all__ = [
    "validate_structured_patch_payload",
    "remove_unused_fallback_id_attributes",
    "repair_relationship_identified_association_multiplicities_payload",
]
