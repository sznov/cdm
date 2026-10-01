from __future__ import annotations

from typing import Any

from harnesses.structured_patch.language_word_support import string_distance_at_most_one, structured_concept_key
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_normalization import (
    STRUCTURED_ATTRIBUTE_TYPE_ALIASES,
    STRUCTURED_ATTRIBUTE_TYPES,
    normalize_structured_name,
)


def relationship_name_for_typed_attribute(
    *,
    base_name: str,
    existing_relationship_names: set[str],
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str:
    normalized = normalize_structured_name(
        base_name,
        style="lower",
        name_policy=name_policy,
    )
    if not isinstance(normalized, str) or not normalized:
        normalized = "povezanoSa"
    existing_keys = {
        name_policy.comparison_key(name)
        for name in existing_relationship_names
    }
    if name_policy.comparison_key(normalized) not in existing_keys:
        return normalized

    suffix = 2
    while name_policy.comparison_key(f"{normalized}{suffix}") in existing_keys:
        suffix += 1
    return f"{normalized}{suffix}"


def entity_target_for_attribute_type(
    raw_type: Any,
    entity_names: set[str],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str | None:
    if not isinstance(raw_type, str):
        return None
    stripped = raw_type.strip()
    if not stripped:
        return None
    if stripped in STRUCTURED_ATTRIBUTE_TYPES:
        return None
    normalized_scalar_type = STRUCTURED_ATTRIBUTE_TYPE_ALIASES.get(stripped.lower())
    if normalized_scalar_type in STRUCTURED_ATTRIBUTE_TYPES:
        return None
    if stripped in entity_names:
        return stripped
    normalized_entity = normalize_structured_name(
        stripped,
        style="upper",
        name_policy=name_policy,
    )
    if isinstance(normalized_entity, str):
        normalized_key = name_policy.comparison_key(normalized_entity)
        for entity_name in entity_names:
            if name_policy.comparison_key(entity_name) == normalized_key:
                return entity_name
    return None


def entity_target_for_attribute_name(
    attribute_name: str,
    entity_names: set[str],
    *,
    source_entity_name: str,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str | None:
    attribute_key = (
        name_policy.comparison_key(attribute_name)
        if name_policy.preserves_unicode
        else structured_concept_key(attribute_name)
    )
    if not attribute_key:
        return None
    candidate_keys = [attribute_key]
    if len(attribute_key) > 2 and attribute_key.endswith("id"):
        candidate_keys.append(attribute_key[:-2])
    for entity_name in sorted(entity_names):
        if name_policy.names_equal(entity_name, source_entity_name):
            continue
        entity_key = (
            name_policy.comparison_key(entity_name)
            if name_policy.preserves_unicode
            else structured_concept_key(entity_name)
        )
        if not entity_key or len(entity_key) < 5:
            continue
        for candidate_key in candidate_keys:
            if candidate_key == entity_key:
                return entity_name
            if min(len(candidate_key), len(entity_key)) >= 8 and string_distance_at_most_one(candidate_key, entity_key):
                return entity_name
            if len(candidate_key) > len(entity_key) and (
                candidate_key.startswith(entity_key) or candidate_key.endswith(entity_key)
            ):
                return entity_name
    return None


def relationship_base_name_for_entity_attribute(attribute_name: str) -> str:
    if len(attribute_name) > 2 and attribute_name.lower().endswith("id"):
        return attribute_name[:-2] or attribute_name
    return attribute_name


__all__ = [
    "entity_target_for_attribute_name",
    "entity_target_for_attribute_type",
    "relationship_base_name_for_entity_attribute",
    "relationship_name_for_typed_attribute",
]
