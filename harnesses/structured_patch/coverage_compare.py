from __future__ import annotations

from typing import Any

from harnesses.structured_patch.coverage_name_similarity import (
    compare_name_similarity,
    compare_name_tokens,
    compare_tokens_match,
)
from harnesses.structured_patch.coverage_overlap import (
    exact_overlap_summary,
    soft_entity_overlap_summary,
    soft_relationship_endpoint_overlap_summary,
)
from core.schemas import StructuredModel, StructuredRelationship


def compare_structured_model_to_reference(
    actual: StructuredModel,
    reference: StructuredModel,
) -> dict[str, Any]:
    actual_entities = {entity.name for entity in actual.entities}
    reference_entities = {entity.name for entity in reference.entities}
    actual_relationship_names = {relationship.name for relationship in actual.relationships if relationship.name}
    reference_relationship_names = {relationship.name for relationship in reference.relationships if relationship.name}
    actual_pairs = {
        (relationship.source.entity, relationship.target.entity)
        for relationship in actual.relationships
        if relationship.source.entity and relationship.target.entity
    }
    reference_pairs = {
        (relationship.source.entity, relationship.target.entity)
        for relationship in reference.relationships
        if relationship.source.entity and relationship.target.entity
    }

    entity_soft_summary, entity_name_map = soft_entity_overlap_summary(actual_entities, reference_entities)

    return {
        "entity_names": exact_overlap_summary(actual_entities, reference_entities),
        "entity_names_soft": entity_soft_summary,
        "relationship_names": exact_overlap_summary(actual_relationship_names, reference_relationship_names),
        "relationship_endpoint_pairs": exact_overlap_summary(actual_pairs, reference_pairs),
        "relationship_endpoint_pairs_soft": soft_relationship_endpoint_overlap_summary(
            actual_pairs,
            reference_pairs,
            entity_name_map,
        ),
    }


def relationship_matches_selector(
    relationship: StructuredRelationship,
    rename: dict[str, str],
) -> bool:
    old = rename.get("old") or ""
    if relationship.name != old:
        return False
    source = rename.get("source") or ""
    target = rename.get("target") or ""
    if source and relationship.source.entity != source:
        return False
    if target and relationship.target.entity != target:
        return False
    return True


__all__ = [
    "compare_name_similarity",
    "compare_name_tokens",
    "compare_structured_model_to_reference",
    "compare_tokens_match",
    "relationship_matches_selector",
    "soft_entity_overlap_summary",
    "soft_relationship_endpoint_overlap_summary",
]
