from __future__ import annotations

from core.schemas import (
    StructuredAttribute,
    StructuredEntity,
    StructuredOutputError,
    StructuredRelationship,
    StructuredRelationshipEnd,
    collect_entity_attribute_map,
)


def resolve_attribute_for_entity(
    entity_name: str,
    attribute_name: str,
    entity_lookup: dict[str, StructuredEntity],
) -> StructuredAttribute:
    attribute = collect_entity_attribute_map(entity_name, entity_lookup).get(attribute_name)
    if attribute is None:
        raise StructuredOutputError(
            f"Structured JSON validation failed. Entity '{entity_name}' is missing attribute '{attribute_name}'."
        )

    return attribute


def identifier_relationship_parent(
    entity_name: str,
    relationship: StructuredRelationship,
) -> tuple[StructuredRelationshipEnd, StructuredRelationshipEnd]:
    if relationship.source.entity == entity_name and relationship.target.entity != entity_name:
        return relationship.target, relationship.source
    if relationship.target.entity == entity_name and relationship.source.entity != entity_name:
        return relationship.source, relationship.target

    raise StructuredOutputError(
        "Structured JSON validation failed. "
        f"Relationship '{relationship.name}' cannot be used as an identifying parent for '{entity_name}'."
    )


def resolve_identifier_relationship(
    entity_name: str,
    relationship_name: str,
    relationships_by_name: dict[str, list[StructuredRelationship]],
) -> StructuredRelationship:
    named_relationships = relationships_by_name.get(relationship_name, [])
    matching_relationships = [
        relationship
        for relationship in named_relationships
        if entity_name in {relationship.source.entity, relationship.target.entity}
    ]
    if not named_relationships:
        raise StructuredOutputError(
            "Structured JSON validation failed. "
            f"Entity '{entity_name}' identifier references missing relationship '{relationship_name}'."
        )
    if not matching_relationships:
        raise StructuredOutputError(
            "Structured JSON validation failed. "
            f"Entity '{entity_name}' identifier relationship '{relationship_name}' does not include that entity."
        )
    if len(matching_relationships) > 1:
        raise StructuredOutputError(
            "Structured JSON validation failed. "
            f"Entity '{entity_name}' identifier relationship '{relationship_name}' is ambiguous for that entity."
        )

    return matching_relationships[0]


__all__ = [
    "identifier_relationship_parent",
    "resolve_attribute_for_entity",
    "resolve_identifier_relationship",
]
