from __future__ import annotations

from typing import Any

from core.schemas import (
    OperationLoopAttribute,
    OperationLoopEntity,
    OperationLoopIdentifierPart,
    OperationLoopRelationship,
    OperationLoopWorkingModel,
    StructuredModel,
)


def structured_model_to_working_model(model: StructuredModel) -> OperationLoopWorkingModel:
    entity_ids = {entity.name: f"E{index}" for index, entity in enumerate(model.entities, start=1)}
    relationship_ids = {
        id(relationship): f"R{index}" for index, relationship in enumerate(model.relationships, start=1)
    }

    relationships_by_name: dict[str, list[Any]] = {}
    for relationship in model.relationships:
        if relationship.name:
            relationships_by_name.setdefault(relationship.name, []).append(relationship)

    entities: list[OperationLoopEntity] = []
    for entity in model.entities:
        identifier: list[OperationLoopIdentifierPart] = []
        for part in entity.identifier:
            ref = part.ref
            if part.kind == "relationship":
                named = relationships_by_name.get(part.ref, [])
                matches = [
                    relationship
                    for relationship in named
                    if entity.name in {relationship.source.entity, relationship.target.entity}
                ]
                if len(matches) == 1:
                    ref = relationship_ids[id(matches[0])]
            identifier.append(OperationLoopIdentifierPart(kind=part.kind, ref=ref))

        entities.append(
            OperationLoopEntity(
                entity_id=entity_ids[entity.name],
                name=entity.name,
                attributes=[
                    OperationLoopAttribute(name=attribute.name, type=attribute.type)
                    for attribute in entity.attributes
                ],
                identifier=identifier,
                inherits_from=[entity_ids.get(parent, parent) for parent in entity.inherits_from],
            )
        )

    relationships: list[OperationLoopRelationship] = []
    for relationship in model.relationships:
        source_name = relationship.source.entity or ""
        target_name = relationship.target.entity or ""
        relationships.append(
            OperationLoopRelationship(
                relationship_id=relationship_ids[id(relationship)],
                name=relationship.name,
                source_entity_id=entity_ids.get(source_name, source_name),
                target_entity_id=entity_ids.get(target_name, target_name),
                source_multiplicity=relationship.source.multiplicity,
                target_multiplicity=relationship.target.multiplicity,
                source_role=relationship.source.role,
                target_role=relationship.target.role,
            )
        )

    return OperationLoopWorkingModel(entities=entities, relationships=relationships)


__all__ = ["structured_model_to_working_model"]
