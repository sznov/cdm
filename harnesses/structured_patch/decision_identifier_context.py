from __future__ import annotations

from typing import Any

from harnesses.structured_patch.decision_merge import merge_decision_patches
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from core.schemas import StructuredModel


def propose_identifier_context_decision_patches(
    model: StructuredModel,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    """Surface optional identity-context patches without applying policy choices silently."""
    entity_lookup = {entity.name: entity for entity in model.entities}
    patches: list[dict[str, Any]] = []
    for entity in model.entities:
        if entity.inherits_from:
            continue
        if not entity.identifier:
            continue
        if any(part.kind == "relationship" for part in entity.identifier):
            continue
        identifier_attributes = {part.ref for part in entity.identifier if part.kind == "attribute"}
        if identifier_attributes == {"id"}:
            continue
        attribute_types = {attribute.name: attribute.type for attribute in entity.attributes}
        has_temporal_identifier = any(attribute_types.get(name) == "date" for name in identifier_attributes)
        if not has_temporal_identifier:
            continue
        for relationship in model.relationships:
            if not relationship.name:
                continue
            source_entity = relationship.source.entity
            target_entity = relationship.target.entity
            if source_entity == entity.name:
                context_entity = target_entity
                entity_multiplicity = relationship.source.multiplicity
                context_multiplicity = relationship.target.multiplicity
            elif target_entity == entity.name:
                context_entity = source_entity
                entity_multiplicity = relationship.target.multiplicity
                context_multiplicity = relationship.source.multiplicity
            else:
                continue
            if not context_entity or context_entity not in entity_lookup:
                continue
            if context_multiplicity not in {"1", "0..1"}:
                continue
            if entity_multiplicity not in {"0..*", "*", "1..*", None}:
                continue
            parts = [{"kind": "relationship", "ref": relationship.name}]
            parts.extend(part.model_dump(mode="json") for part in entity.identifier)
            operation = {"op": "setIdentifier", "entity": entity.name, "parts": parts}
            title = f"Include {context_entity} in {entity.name} identifier"
            apply_label = f"add {context_entity} ({relationship.name}) to {entity.name} identifier"
            patches.append(
                {
                    "id": f"DP{len(patches) + 1}",
                    "status": "pending",
                    "kind": "identifierContext",
                    "title": title,
                    "question": (
                        f"Should {entity.name} be identified by its {context_entity} context plus "
                        "the stated scalar identifier?"
                    ),
                    "reason": (
                        "The entity has a temporal scalar identifier and a mandatory context relationship. "
                        "This may be a real-world uniqueness decision rather than an automatic correction."
                    ),
                    "evidence": "",
                    "operation": operation,
                    "apply_label": apply_label,
                    "options": [
                        {"id": "apply", "label": apply_label, "operation": operation},
                        {"id": "keep", "label": "keep as-is", "operation": None},
                        {"id": "custom", "label": "something else", "operation": None, "requires_text": True},
                    ],
                    "source": "deterministic_identifier_context_scan",
                }
            )
    return merge_decision_patches(patches, name_policy=name_policy)


__all__ = ["propose_identifier_context_decision_patches"]
