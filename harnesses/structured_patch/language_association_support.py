from __future__ import annotations

from core.naming import split_identifier_words, to_lower_camel_ascii, to_upper_camel_ascii
from harnesses.structured_patch.language_word_support import repair_name_support, supported_words_in_name
from core.schemas import StructuredEntity, StructuredModel


def relationship_count_for_entity(model: StructuredModel, entity_name: str) -> int:
    return sum(
        1
        for relationship in model.relationships
        if relationship.source.entity == entity_name or relationship.target.entity == entity_name
    )


def entity_supported_fact_names(
    *,
    entity: StructuredEntity,
    renames: list[dict[str, str]],
    spec_words: set[str],
) -> list[str]:
    candidate_names: list[str] = []
    for rename in renames:
        if (rename.get("kind") or "").strip() != "attribute":
            continue
        if (rename.get("entity") or "").strip() != entity.name:
            continue
        candidate = to_lower_camel_ascii((rename.get("new") or "").strip(), fallback="")
        if candidate:
            candidate_names.append(candidate)
    candidate_names.extend(attribute.name for attribute in entity.attributes)

    supported: list[str] = []
    for candidate in candidate_names:
        if candidate.lower() == "id":
            continue
        words = [word for word in split_identifier_words(candidate) if len(word) > 2]
        if not words:
            continue
        if repair_name_support(candidate, spec_words=spec_words)["supported"]:
            supported.append(candidate)
    return supported


def association_entity_can_accept_partially_supported_name(
    *,
    entity: StructuredEntity,
    model: StructuredModel,
    proposed_name: str,
    renames: list[dict[str, str]],
    spec_words: set[str],
) -> bool:
    if relationship_count_for_entity(model, entity.name) < 2:
        return False
    if not entity_supported_fact_names(entity=entity, renames=renames, spec_words=spec_words):
        return False
    return bool(supported_words_in_name(proposed_name, spec_words=spec_words))


def supported_association_entity_fallback_name(
    *,
    entity: StructuredEntity,
    model: StructuredModel,
    renames: list[dict[str, str]],
    spec_words: set[str],
) -> str | None:
    if relationship_count_for_entity(model, entity.name) < 2:
        return None

    for candidate in entity_supported_fact_names(entity=entity, renames=renames, spec_words=spec_words):
        return to_upper_camel_ascii(candidate, fallback="")
    return None


__all__ = [
    "relationship_count_for_entity",
    "entity_supported_fact_names",
    "association_entity_can_accept_partially_supported_name",
    "supported_association_entity_fallback_name",
]
