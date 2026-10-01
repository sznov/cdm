from __future__ import annotations

from core.plantuml_common import (
    PLANTUML_HEADER,
    format_left_relationship_part,
    format_plantuml_type,
    format_relationship_end_label,
    format_right_relationship_part,
    simplify_plantuml_relationship_name,
)
from core.plantuml_identifiers import (
    identifier_relationship_parent,
    resolve_attribute_for_entity,
    resolve_identifier_relationship,
)
from core.schemas import (
    StructuredModel,
    StructuredOutputError,
    get_entity_lookup,
    get_relationships_by_name,
)


def render_structured_model_to_plantuml(model: StructuredModel) -> str:
    entity_lookup = get_entity_lookup(model)
    relationships_by_name = get_relationships_by_name(model)
    identifying_relationship_children: dict[int, str] = {}

    for entity in model.entities:
        for identifier_part in entity.identifier:
            if identifier_part.kind != "relationship":
                continue

            relationship = resolve_identifier_relationship(entity.name, identifier_part.ref, relationships_by_name)
            relationship_key = id(relationship)
            if relationship_key in identifying_relationship_children:
                existing_child = identifying_relationship_children[relationship_key]
                if existing_child != entity.name:
                    raise StructuredOutputError(
                        "Structured JSON validation failed. "
                        f"Relationship '{identifier_part.ref}' is used to identify multiple entities."
                    )
            identifying_relationship_children[relationship_key] = entity.name
            identifier_relationship_parent(entity.name, relationship)

    lines = PLANTUML_HEADER.copy()

    for entity in model.entities:
        lines.append(f"class {entity.name} {{")
        for attribute in entity.attributes:
            lines.append(f"  {attribute.name}: {format_plantuml_type(attribute.type)}")

        attribute_identifier_parts = [part.ref for part in entity.identifier if part.kind == "attribute"]
        relationship_identifier_parts = [part.ref for part in entity.identifier if part.kind == "relationship"]
        if relationship_identifier_parts:
            if attribute_identifier_parts:
                signature = ", ".join(
                    (
                        f"{attribute_name}: "
                        f"{format_plantuml_type(resolve_attribute_for_entity(entity.name, attribute_name, entity_lookup).type)}"
                    )
                    for attribute_name in attribute_identifier_parts
                )
                lines.append(f"  PK_D({signature})")
        elif attribute_identifier_parts:
            signature = ", ".join(
                (
                    f"{attribute_name}: "
                    f"{format_plantuml_type(resolve_attribute_for_entity(entity.name, attribute_name, entity_lookup).type)}"
                )
                for attribute_name in attribute_identifier_parts
            )
            lines.append(f"  PK({signature})")

        lines.append("}")
        lines.append("")

    for entity in model.entities:
        for parent_name in entity.inherits_from:
            lines.append(f"{parent_name} <|-- {entity.name}")

    if any(entity.inherits_from for entity in model.entities):
        lines.append("")

    for relationship in model.relationships:
        display_name = simplify_plantuml_relationship_name(
            relationship.name,
            relationship.source.entity or "",
            relationship.target.entity or "",
        )
        child_name = identifying_relationship_children.get(id(relationship))
        if child_name:
            parent_end, child_end = identifier_relationship_parent(child_name, relationship)
            parent_label = format_relationship_end_label(parent_end, include_role=False)
            child_label = format_relationship_end_label(child_end, include_role=False)
            composition_line = (
                f"{format_left_relationship_part(parent_end.entity or '', parent_label)} *-- "
                f"{format_right_relationship_part(child_end.entity or '', child_label)}"
            )
            if display_name:
                composition_line += f" : {display_name}"
            lines.append(composition_line)
            continue

        source_label = format_relationship_end_label(relationship.source, include_role=False)
        target_label = format_relationship_end_label(relationship.target, include_role=False)
        association_line = (
            f"{format_left_relationship_part(relationship.source.entity or '', source_label)} -- "
            f"{format_right_relationship_part(relationship.target.entity or '', target_label)}"
        )
        if display_name:
            association_line += f" : {display_name}"
        lines.append(association_line)

    lines.append("@enduml")
    return "\n".join(lines)


__all__ = ["render_structured_model_to_plantuml"]
