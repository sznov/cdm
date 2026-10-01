from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_model_lookup import structured_entity_attribute_names
from harnesses.structured_patch.patch_scalar_normalization import (
    normalize_structured_attribute_type,
    normalize_structured_multiplicity,
    normalize_structured_name,
)


def add_missing_surrogate_id_identifier_attributes(
    model_payload: dict[str, Any],
    entity: dict[str, Any],
    identifier_parts: list[dict[str, str]],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    entity_name = str(entity.get("name") or "")
    if not entity_name:
        return []
    inherited_attribute_names = structured_entity_attribute_names(
        model_payload,
        entity_name,
        name_policy=name_policy,
    )
    if any(name_policy.names_equal("id", name) for name in inherited_attribute_names):
        return []
    if not any(
        part.get("kind") == "attribute" and name_policy.names_equal(part.get("ref"), "id")
        for part in identifier_parts
    ):
        return []
    entity.setdefault("attributes", []).append({"name": "id", "type": "int"})
    return [
        {
            "kind": "deterministic_repair",
            "check_id": "surrogate_identifier_attribute",
            "entity": entity_name,
            "attribute": "id",
            "summary": f"Added {entity_name}.id as the surrogate identifier attribute requested by setIdentifier.",
        }
    ]


def normalize_structured_attributes_payload(
    raw_attributes: Any,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, str]]:
    if raw_attributes is None:
        return []
    if isinstance(raw_attributes, dict):
        raw_attributes = [{"name": name, "type": value} for name, value in raw_attributes.items()]
    if not isinstance(raw_attributes, list):
        return []
    attributes: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_attribute in raw_attributes:
        if not isinstance(raw_attribute, dict):
            continue
        name = normalize_structured_name(raw_attribute.get("name"), style="lower", name_policy=name_policy)
        name_key = name_policy.comparison_key(name)
        if not isinstance(name, str) or not name or name_key in seen:
            continue
        seen.add(name_key)
        attributes.append({"name": name, "type": normalize_structured_attribute_type(raw_attribute.get("type"))})
    return attributes


def normalize_structured_identifier_parts(
    raw_parts: Any,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, str]]:
    if isinstance(raw_parts, dict) and isinstance(raw_parts.get("parts"), list):
        raw_parts = raw_parts["parts"]
    if not isinstance(raw_parts, list):
        return []
    parts: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw_part in raw_parts:
        if not isinstance(raw_part, dict):
            continue
        kind = str(raw_part.get("kind") or "").strip()
        if kind not in {"attribute", "relationship"}:
            continue
        ref_style = "lower"
        ref = normalize_structured_name(
            raw_part.get("ref") or raw_part.get("name"),
            style=ref_style,
            name_policy=name_policy,
        )
        if not isinstance(ref, str) or not ref:
            continue
        key = (kind, name_policy.comparison_key(ref))
        if key in seen:
            continue
        seen.add(key)
        parts.append({"kind": kind, "ref": ref})
    return parts


def normalize_structured_relationship_end_payload(
    raw_end: Any,
    *,
    fallback_entity: Any = None,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any]:
    if isinstance(raw_end, str):
        raw_end = {"entity": raw_end}
    if not isinstance(raw_end, dict):
        raw_end = {}
    entity = normalize_structured_name(
        raw_end.get("entity") or fallback_entity,
        style="upper",
        name_policy=name_policy,
    )
    end: dict[str, Any] = {"entity": entity}
    multiplicity = normalize_structured_multiplicity(raw_end.get("multiplicity"))
    if multiplicity:
        end["multiplicity"] = multiplicity
    role = (
        normalize_structured_name(raw_end.get("role"), style="lower", name_policy=name_policy)
        if raw_end.get("role")
        else None
    )
    if role:
        end["role"] = role
    return end


def normalize_structured_relationship_payload(
    operation: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any]:
    name = operation.get("name") or operation.get("relationship") or operation.get("relationshipName")
    source = (
        operation.get("source")
        or operation.get("from")
        or operation.get("source_entity")
        or operation.get("sourceEntity")
        or operation.get("source_entity_id")
        or operation.get("sourceEntityId")
    )
    target = (
        operation.get("target")
        or operation.get("to")
        or operation.get("target_entity")
        or operation.get("targetEntity")
        or operation.get("target_entity_id")
        or operation.get("targetEntityId")
    )
    relationship: dict[str, Any] = {
        "source": normalize_structured_relationship_end_payload(source, name_policy=name_policy),
        "target": normalize_structured_relationship_end_payload(target, name_policy=name_policy),
    }
    normalized_name = (
        normalize_structured_name(name, style="lower", name_policy=name_policy)
        if name
        else None
    )
    if normalized_name:
        relationship["name"] = normalized_name
    return relationship


def structured_relationship_matches(
    relationship: dict[str, Any],
    *,
    name: str | None = None,
    source: str | None = None,
    target: str | None = None,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> bool:
    if name and not name_policy.names_equal(relationship.get("name"), name):
        return False
    source_entity = (relationship.get("source") or {}).get("entity") if isinstance(relationship.get("source"), dict) else None
    target_entity = (relationship.get("target") or {}).get("entity") if isinstance(relationship.get("target"), dict) else None
    if source and not name_policy.names_equal(source_entity, source):
        return False
    if target and not name_policy.names_equal(target_entity, target):
        return False
    return True


__all__ = [
    "add_missing_surrogate_id_identifier_attributes",
    "normalize_structured_attributes_payload",
    "normalize_structured_identifier_parts",
    "normalize_structured_relationship_end_payload",
    "normalize_structured_relationship_payload",
    "structured_relationship_matches",
]
