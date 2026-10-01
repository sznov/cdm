from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Multiplicity = Literal["0..1", "1", "0..*", "*", "1..*"]


def normalize_multiplicity(value: Any) -> Any:
    if value is None:
        return value
    text = str(value).strip()
    if text == "*":
        return "0..*"
    normalized = (
        text.lower()
        .replace(" ", "")
        .replace("…", "..")
        .replace("...", "..")
        .replace("∞", "*")
    )
    aliases = {
        "1..1": "1",
        "one": "1",
        "exactlyone": "1",
        "many": "0..*",
        "n": "0..*",
        "m": "0..*",
        "0..n": "0..*",
        "0..m": "0..*",
        "0..many": "0..*",
        "1..n": "1..*",
        "1..m": "1..*",
        "1..many": "1..*",
    }
    if normalized in aliases:
        return aliases[normalized]
    if re.fullmatch(r"[2-9]\d*\.\.\*", normalized):
        return "1..*"
    return text


class StructuredAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: Literal["string", "int", "real", "bool", "date"]


class StructuredIdentifierPart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["attribute", "relationship"]
    ref: str


class StructuredEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    attributes: list[StructuredAttribute] = Field(default_factory=list)
    identifier: list[StructuredIdentifierPart] = Field(default_factory=list)
    inherits_from: list[str] = Field(default_factory=list)

    @field_validator("attributes", "identifier", "inherits_from", mode="before")
    @classmethod
    def default_optional_lists(cls, value: Any) -> Any:
        if value is None:
            return []
        return value


class StructuredRelationshipEnd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: str | None = None
    multiplicity: Multiplicity | None = None
    role: str | None = None

    @field_validator("multiplicity", mode="before")
    @classmethod
    def normalize_star_multiplicity(cls, value: Any) -> Any:
        return normalize_multiplicity(value)


class StructuredRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    source: StructuredRelationshipEnd
    target: StructuredRelationshipEnd


class StructuredModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[StructuredEntity]
    relationships: list[StructuredRelationship]


class StructuredOutputError(ValueError):
    pass


class CanonicalEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)

    @field_validator("aliases", "evidence", mode="before")
    @classmethod
    def default_optional_lists(cls, value: Any) -> Any:
        if value is None:
            return []
        return value


class CanonicalRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[CanonicalEntity]


class CanonicalOutputError(ValueError):
    pass


class OperationLoopError(ValueError):
    pass


class OperationLoopAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    type: Literal["string", "int", "real", "bool", "date"]
    evidence: list[str] = Field(default_factory=list)


class OperationLoopIdentifierPart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["attribute", "relationship"]
    ref: str


class OperationLoopEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    attributes: list[OperationLoopAttribute] = Field(default_factory=list)
    identifier: list[OperationLoopIdentifierPart] = Field(default_factory=list)
    inherits_from: list[str] = Field(default_factory=list)


class OperationLoopRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relationship_id: str
    name: str | None = None
    source_entity_id: str
    target_entity_id: str
    source_multiplicity: Multiplicity | None = None
    target_multiplicity: Multiplicity | None = None
    source_role: str | None = None
    target_role: str | None = None
    evidence: list[str] = Field(default_factory=list)

    @field_validator("source_multiplicity", "target_multiplicity", mode="before")
    @classmethod
    def normalize_star_multiplicity(cls, value: Any) -> Any:
        return normalize_multiplicity(value)


class OperationLoopPendingTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    kind: Literal["identifier_relationship"]
    entity_id: str
    relationship_id: str
    attribute_refs: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    reason: str = ""


class OperationLoopPlanTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    description: str
    status: Literal["pending", "done"] = "pending"
    evidence: list[str] = Field(default_factory=list)


class OperationLoopWorkingModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[OperationLoopEntity] = Field(default_factory=list)
    relationships: list[OperationLoopRelationship] = Field(default_factory=list)
    pending_tasks: list[OperationLoopPendingTask] = Field(default_factory=list)
    plan_tasks: list[OperationLoopPlanTask] = Field(default_factory=list)
    entity_id_aliases: dict[str, str] = Field(default_factory=dict)
    relationship_id_aliases: dict[str, str] = Field(default_factory=dict)


class OperationLoopBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["continue", "done"] = "continue"
    focus: str = ""
    evidence: list[str] = Field(default_factory=list)
    op: dict[str, Any] | None = None
    # Kept for internal tests/helpers; model-facing parsing rejects this key.
    ops: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("decision", mode="before")
    @classmethod
    def normalize_decision(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("evidence", mode="before")
    @classmethod
    def normalize_evidence(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return value


def get_entity_lookup(model: StructuredModel) -> dict[str, StructuredEntity]:
    return {entity.name: entity for entity in model.entities}


def get_relationships_by_name(model: StructuredModel) -> dict[str, list[StructuredRelationship]]:
    relationships_by_name: dict[str, list[StructuredRelationship]] = {}
    for relationship in model.relationships:
        if not relationship.name:
            continue
        relationships_by_name.setdefault(relationship.name, []).append(relationship)

    return relationships_by_name


def collect_entity_attribute_map(
    entity_name: str,
    entity_lookup: dict[str, StructuredEntity],
    *,
    visiting: set[str] | None = None,
) -> dict[str, StructuredAttribute]:
    if visiting is None:
        visiting = set()

    if entity_name in visiting or entity_name not in entity_lookup:
        return {}

    visiting.add(entity_name)
    entity = entity_lookup[entity_name]
    attributes = {attribute.name: attribute for attribute in entity.attributes}
    for parent_name in entity.inherits_from:
        parent_attributes = collect_entity_attribute_map(parent_name, entity_lookup, visiting=visiting.copy())
        for name, attribute in parent_attributes.items():
            attributes.setdefault(name, attribute)

    return attributes


def validate_structured_model_links(model: StructuredModel) -> None:
    errors: list[str] = []
    entity_lookup = get_entity_lookup(model)
    relationships_by_name = get_relationships_by_name(model)

    if len(entity_lookup) != len(model.entities):
        errors.append("Entity names must be unique.")

    for entity in model.entities:
        attribute_names = [attribute.name for attribute in entity.attributes]
        if len(set(attribute_names)) != len(attribute_names):
            errors.append(f"Entity '{entity.name}' contains duplicate attribute names.")

        for parent_name in entity.inherits_from:
            if parent_name == entity.name:
                errors.append(f"Entity '{entity.name}' cannot inherit from itself.")
            elif parent_name not in entity_lookup:
                errors.append(f"Entity '{entity.name}' inherits from missing entity '{parent_name}'.")

        inherited_attributes = collect_entity_attribute_map(entity.name, entity_lookup)
        for identifier_part in entity.identifier:
            if identifier_part.kind == "attribute":
                if identifier_part.ref not in inherited_attributes:
                    errors.append(
                        f"Entity '{entity.name}' identifier references missing attribute '{identifier_part.ref}'."
                    )
                continue

            named_relationships = relationships_by_name.get(identifier_part.ref, [])
            matching_relationships = [
                relationship
                for relationship in named_relationships
                if entity.name in {relationship.source.entity, relationship.target.entity}
            ]
            if not named_relationships:
                errors.append(
                    f"Entity '{entity.name}' identifier references missing relationship '{identifier_part.ref}'."
                )
                continue
            elif not matching_relationships:
                errors.append(
                    f"Entity '{entity.name}' identifier relationship '{identifier_part.ref}' does not include that entity."
                )
                continue
            elif len(matching_relationships) > 1:
                errors.append(
                    f"Entity '{entity.name}' identifier relationship '{identifier_part.ref}' is ambiguous for that entity."
                )
                continue

            relationship = matching_relationships[0]
            if relationship.source.entity == relationship.target.entity:
                errors.append(
                    f"Entity '{entity.name}' identifier relationship '{identifier_part.ref}' is self-referential and ambiguous."
                )

    for relationship in model.relationships:
        relationship_label = relationship.name or "<unnamed relationship>"
        if not relationship.source.entity:
            errors.append(f"Relationship '{relationship_label}' is missing source.entity.")
        elif relationship.source.entity not in entity_lookup:
            errors.append(
                f"Relationship '{relationship_label}' references missing source entity '{relationship.source.entity}'."
            )
        if not relationship.target.entity:
            errors.append(f"Relationship '{relationship_label}' is missing target.entity.")
        elif relationship.target.entity not in entity_lookup:
            errors.append(
                f"Relationship '{relationship_label}' references missing target entity '{relationship.target.entity}'."
            )

    if errors:
        raise StructuredOutputError("Structured JSON validation failed. " + " ".join(errors))

