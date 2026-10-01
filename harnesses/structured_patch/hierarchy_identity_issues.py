from __future__ import annotations

import json
from typing import Any

from harnesses.structured_patch.model_issue_merge import merge_structured_model_issue_lists
from core.schemas import StructuredModel


def structured_children_by_parent(model: StructuredModel) -> dict[str, list[str]]:
    children_by_parent: dict[str, list[str]] = {}
    for entity in model.entities:
        for parent_name in entity.inherits_from:
            children_by_parent.setdefault(parent_name, []).append(entity.name)
    return children_by_parent


def effective_identifier_sources_for_entity(
    entity_name: str,
    entity_lookup: dict[str, Any],
    *,
    visiting: set[str] | None = None,
) -> list[dict[str, Any]]:
    if visiting is None:
        visiting = set()
    if entity_name in visiting or entity_name not in entity_lookup:
        return []
    visiting.add(entity_name)
    entity = entity_lookup[entity_name]
    if entity.identifier:
        return [{"entity": entity.name, "identifier": [part.model_dump(mode="json") for part in entity.identifier]}]
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for parent_name in entity.inherits_from:
        for source in effective_identifier_sources_for_entity(parent_name, entity_lookup, visiting=visiting.copy()):
            key = json.dumps(source, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                sources.append(source)
    return sources


def structured_hierarchy_identity_issues(model: StructuredModel) -> list[dict[str, Any]]:
    """Return model-structural hierarchy and identifier issues.

    This validator does not inspect or infer evidence from specification text. The
    legacy evidence wording below is retained unchanged for protocol compatibility.
    """
    entity_lookup = {entity.name: entity for entity in model.entities}
    children_by_parent = structured_children_by_parent(model)
    issues: list[dict[str, Any]] = []

    for entity in model.entities:
        child_names = children_by_parent.get(entity.name, [])
        own_identifier = [part.model_dump(mode="json") for part in entity.identifier]
        parent_sources: list[dict[str, Any]] = []
        for parent_name in entity.inherits_from:
            parent_sources.extend(
                effective_identifier_sources_for_entity(parent_name, entity_lookup, visiting={entity.name})
            )
        parent_source_keys = {
            json.dumps(source, sort_keys=True, ensure_ascii=False)
            for source in parent_sources
            if source.get("identifier")
        }
        effective_sources = (
            [{"entity": entity.name, "identifier": own_identifier}]
            if own_identifier
            else effective_identifier_sources_for_entity(entity.name, entity_lookup)
        )

        if not effective_sources and not child_names:
            issues.append(
                {
                    "id": f"HID{len(issues) + 1}",
                    "kind": "hardError",
                    "target": f"{entity.name}.identifier",
                    "summary": (
                        f"Concrete entity '{entity.name}' has no effective identifier through itself or its parents."
                    ),
                    "evidence": "",
                    "options": [],
                }
            )

        if own_identifier and len(parent_source_keys) == 1:
            issues.append(
                {
                    "id": f"HID{len(issues) + 1}",
                    "kind": "decision",
                    "target": f"{entity.name}.identifier",
                    "summary": (
                        f"Subtype '{entity.name}' defines its own identifier while a parent identifier is also available."
                    ),
                    "evidence": "Subtype-specific identity may be intentional when supported by the specification.",
                    "options": [],
                }
            )
        elif not own_identifier and len(parent_source_keys) > 1:
            issues.append(
                {
                    "id": f"HID{len(issues) + 1}",
                    "kind": "decision",
                    "target": f"{entity.name}.identifier",
                    "summary": (
                        f"Entity '{entity.name}' inherits multiple different parent identifiers; effective identity is ambiguous."
                    ),
                    "evidence": "",
                    "options": [],
                }
            )

    return merge_structured_model_issue_lists(issues)


__all__ = [
    "effective_identifier_sources_for_entity",
    "structured_children_by_parent",
    "structured_hierarchy_identity_issues",
]
