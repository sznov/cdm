from __future__ import annotations

from typing import Any

from core.naming import split_identifier_words, to_upper_camel_ascii
from harnesses.structured_patch.model_conversion import structured_model_to_working_model
from harnesses.structured_patch.patch_deltas import relationship_context_payload
from core.plantuml_structured import render_structured_model_to_plantuml
from core.schemas import StructuredModel

def touched_names_from_patch_delta(delta: dict[str, Any], patch_task: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("target", "summary", "evidence"):
        value = str(patch_task.get(key) or "")
        if value:
            names.add(to_upper_camel_ascii(value))
        for word in split_identifier_words(value):
            if word and word[:1].isupper():
                names.add(to_upper_camel_ascii(word))
    for scope in patch_task.get("allowed_scope") or []:
        scope_name = to_upper_camel_ascii(str(scope))
        if scope_name:
            names.add(scope_name)
    for key in ("added_entities", "removed_entities", "changed_entities"):
        for name in delta.get(key) or []:
            names.add(str(name))
    for relationship in (delta.get("added_relationships") or []) + (delta.get("removed_relationships") or []):
        if not isinstance(relationship, dict):
            continue
        for end_key in ("source", "target"):
            end = relationship.get(end_key)
            if isinstance(end, dict) and end.get("entity"):
                names.add(str(end["entity"]))
    for relationship_change in delta.get("changed_relationships") or []:
        if not isinstance(relationship_change, dict):
            continue
        for relationship in (relationship_change.get("before"), relationship_change.get("after")):
            if not isinstance(relationship, dict):
                continue
            for end_key in ("source", "target"):
                end = relationship.get(end_key)
                if isinstance(end, dict) and end.get("entity"):
                    names.add(str(end["entity"]))
    return names


def structured_model_local_context(model: StructuredModel, touched_names: set[str]) -> dict[str, Any]:
    entity_names = {entity.name for entity in model.entities}
    selected_names = {name for name in touched_names if name in entity_names}
    selected_relationships = []
    for relationship in model.relationships:
        if (relationship.source.entity in selected_names) or (relationship.target.entity in selected_names):
            selected_relationships.append(relationship_context_payload(relationship))
            if relationship.source.entity:
                selected_names.add(relationship.source.entity)
            if relationship.target.entity:
                selected_names.add(relationship.target.entity)
    selected_entities = [
        entity.model_dump(mode="json")
        for entity in model.entities
        if entity.name in selected_names
    ]
    return {
        "entities": selected_entities,
        "relationships": selected_relationships,
    }


def structured_model_event_payload(model: StructuredModel) -> dict[str, Any]:
    working_model = structured_model_to_working_model(model)
    plantuml = render_structured_model_to_plantuml(model)
    return {
        "model_snapshot": working_model.model_dump(mode="json"),
        "structured_model": model.model_dump(mode="json"),
        "plantuml": plantuml,
        "plantuml_url": "",
    }

__all__ = [
    "structured_model_event_payload",
    "structured_model_local_context",
    "touched_names_from_patch_delta",
]
