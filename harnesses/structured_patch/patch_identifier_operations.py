from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_normalization import (
    add_missing_surrogate_id_identifier_attributes,
    find_structured_entity_payload,
    normalize_structured_identifier_parts,
    structured_entity_attribute_names,
)
from core.schemas import StructuredOutputError


def apply_identifier_patch_operation(
    payload: dict[str, Any],
    op: dict[str, Any],
    deterministic_repairs: list[dict[str, Any]],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    entity = find_structured_entity_payload(
        payload,
        op.get("entity") or op.get("entityName"),
        name_policy=name_policy,
    )
    if entity is None:
        raise StructuredOutputError("setIdentifier references a missing entity.")
    parts = normalize_structured_identifier_parts(
        op.get("parts") or op.get("identifier"),
        name_policy=name_policy,
    )
    relationship_names = {
        str(relationship.get("name") or "")
        for relationship in payload.get("relationships") or []
        if isinstance(relationship, dict) and str(relationship.get("name") or "")
    }
    attribute_names = structured_entity_attribute_names(
        payload,
        str(entity.get("name") or ""),
        name_policy=name_policy,
    )
    for part in parts:
        candidates = relationship_names if part.get("kind") == "relationship" else attribute_names
        canonical_ref = next(
            (
                candidate
                for candidate in candidates
                if name_policy.names_equal(part.get("ref"), candidate)
            ),
            None,
        )
        if canonical_ref is not None:
            part["ref"] = canonical_ref
    missing_relationship_refs = sorted(
        {
            str(part.get("ref") or "")
            for part in parts
            if isinstance(part, dict)
            and part.get("kind") == "relationship"
            and not any(
                name_policy.names_equal(part.get("ref"), relationship_name)
                for relationship_name in relationship_names
            )
        }
    )
    if missing_relationship_refs:
        return {
            "status": "deferred",
            "op": op,
            "missing_relationships": missing_relationship_refs,
            "reason": "Identifier relationship reference is missing.",
        }
    identifier_attribute_repairs = add_missing_surrogate_id_identifier_attributes(
        payload,
        entity,
        parts,
        name_policy=name_policy,
    )
    deterministic_repairs.extend(identifier_attribute_repairs)
    if entity.get("identifier") == parts and not identifier_attribute_repairs:
        return {"status": "already_satisfied", "op": op, "reason": "Identifier is already set."}
    entity["identifier"] = parts
    return None


__all__ = ["apply_identifier_patch_operation"]
