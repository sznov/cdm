from __future__ import annotations

from typing import Any

from core.schemas import StructuredModel, StructuredRelationship


def relationship_context_payload(relationship: StructuredRelationship) -> dict[str, Any]:
    return relationship.model_dump(mode="json")


def relationship_identity(relationship: StructuredRelationship) -> tuple[str, str, str]:
    return (
        relationship.name or "",
        relationship.source.entity or "",
        relationship.target.entity or "",
    )


def summarize_structured_model_delta(before: StructuredModel, after: StructuredModel) -> dict[str, Any]:
    before_entities = {entity.name: entity for entity in before.entities}
    after_entities = {entity.name: entity for entity in after.entities}
    added_entities = sorted(set(after_entities) - set(before_entities))
    removed_entities = sorted(set(before_entities) - set(after_entities))
    changed_entities = sorted(
        name
        for name in set(before_entities) & set(after_entities)
        if before_entities[name].model_dump(mode="json") != after_entities[name].model_dump(mode="json")
    )

    before_relationships = {relationship_identity(relationship): relationship for relationship in before.relationships}
    after_relationships = {relationship_identity(relationship): relationship for relationship in after.relationships}
    added_relationship_keys = sorted(set(after_relationships) - set(before_relationships))
    removed_relationship_keys = sorted(set(before_relationships) - set(after_relationships))
    changed_relationship_keys = sorted(
        key
        for key in set(before_relationships) & set(after_relationships)
        if before_relationships[key].model_dump(mode="json") != after_relationships[key].model_dump(mode="json")
    )

    return {
        "entity_count_before": len(before.entities),
        "entity_count_after": len(after.entities),
        "relationship_count_before": len(before.relationships),
        "relationship_count_after": len(after.relationships),
        "added_entities": added_entities,
        "removed_entities": removed_entities,
        "changed_entities": changed_entities,
        "added_relationships": [relationship_context_payload(after_relationships[key]) for key in added_relationship_keys],
        "removed_relationships": [relationship_context_payload(before_relationships[key]) for key in removed_relationship_keys],
        "changed_relationships": [
            {
                "before": relationship_context_payload(before_relationships[key]),
                "after": relationship_context_payload(after_relationships[key]),
            }
            for key in changed_relationship_keys
        ],
    }


__all__ = [
    "relationship_context_payload",
    "relationship_identity",
    "summarize_structured_model_delta",
]
