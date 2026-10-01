from __future__ import annotations

from core.schemas import StructuredRelationshipEnd

PLANTUML_TYPE_LABELS = {
    "string": "String",
    "int": "Integer",
    "real": "Real",
    "bool": "Boolean",
    "date": "Date",
}
PLANTUML_HEADER = [
    "@startuml",
    "hide circle",
    "",
]


def format_plantuml_type(type_name: str) -> str:
    return PLANTUML_TYPE_LABELS.get(type_name, type_name)


def format_relationship_end_label(end: StructuredRelationshipEnd, *, include_role: bool = True) -> str | None:
    label = end.multiplicity or ""
    role = (end.role or "").strip() if include_role else ""
    if role:
        label = f"{label}\\n{role}" if label else role

    if not label:
        return None

    return f'"{label}"'


def format_left_relationship_part(entity_name: str, label: str | None) -> str:
    return f"{entity_name} {label}" if label else entity_name


def format_right_relationship_part(entity_name: str, label: str | None) -> str:
    return f"{label} {entity_name}" if label else entity_name


def simplify_plantuml_relationship_name(name: str | None, source_entity: str, target_entity: str) -> str:
    original = (name or "").strip()
    return original


__all__ = [
    "PLANTUML_HEADER",
    "PLANTUML_TYPE_LABELS",
    "format_left_relationship_part",
    "format_plantuml_type",
    "format_relationship_end_label",
    "format_right_relationship_part",
    "simplify_plantuml_relationship_name",
]
