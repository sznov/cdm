from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_scalar_normalization import normalize_structured_name
from core.schemas import StructuredModel, validate_structured_model_links


def structured_model_from_payload(payload: dict[str, Any]) -> StructuredModel:
    model = StructuredModel.model_validate(payload)
    validate_structured_model_links(model)
    return model


def structured_entity_names(model_payload: dict[str, Any]) -> set[str]:
    return {
        str(entity.get("name") or "")
        for entity in model_payload.get("entities") or []
        if isinstance(entity, dict) and str(entity.get("name") or "")
    }


def resolve_structured_entity_name(
    raw_name: Any,
    model_payload: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str:
    name = str(raw_name or "").strip()
    names = structured_entity_names(model_payload)
    for existing_name in names:
        if name_policy.names_equal(name, existing_name):
            return existing_name
    normalized = normalize_structured_name(name, style="upper", name_policy=name_policy)
    if isinstance(normalized, str):
        for existing_name in names:
            if name_policy.names_equal(normalized, existing_name):
                return existing_name
    return str(normalized or name)


def structured_entity_name_from_ref(
    raw_ref: Any,
    model_payload: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str:
    if isinstance(raw_ref, dict):
        raw_ref = raw_ref.get("entity") or raw_ref.get("name")
    return resolve_structured_entity_name(raw_ref, model_payload, name_policy=name_policy)


def find_structured_entity_payload(
    model_payload: dict[str, Any],
    raw_name: Any,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    name = resolve_structured_entity_name(raw_name, model_payload, name_policy=name_policy)
    for entity in model_payload.get("entities") or []:
        if isinstance(entity, dict) and name_policy.names_equal(entity.get("name"), name):
            return entity
    return None


def structured_entity_attribute_names(
    model_payload: dict[str, Any],
    entity_name: str,
    visited: set[str] | None = None,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> set[str]:
    visited = visited or set()
    resolved_name = resolve_structured_entity_name(entity_name, model_payload, name_policy=name_policy)
    resolved_key = name_policy.comparison_key(resolved_name)
    if not resolved_name or resolved_key in visited:
        return set()
    visited.add(resolved_key)
    entity = find_structured_entity_payload(model_payload, resolved_name, name_policy=name_policy)
    if not isinstance(entity, dict):
        return set()
    names = {
        str(attribute.get("name") or "")
        for attribute in entity.get("attributes") or []
        if isinstance(attribute, dict) and str(attribute.get("name") or "")
    }
    for parent in entity.get("inherits_from") or []:
        names.update(
            structured_entity_attribute_names(
                model_payload,
                str(parent or ""),
                visited,
                name_policy=name_policy,
            )
        )
    return names


__all__ = [
    "structured_model_from_payload",
    "structured_entity_names",
    "resolve_structured_entity_name",
    "structured_entity_name_from_ref",
    "find_structured_entity_payload",
    "structured_entity_attribute_names",
]
