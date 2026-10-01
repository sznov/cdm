from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_scalar_normalization import normalize_structured_name

def add_missing_endpoint_entities(
    repaired: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any]:
    entity_names = {
        name_policy.comparison_key(entity.get("name")):
        str(entity.get("name") or "")
        for entity in repaired.get("entities", [])
        if isinstance(entity, dict) and str(entity.get("name") or "")
    }
    for relationship in repaired.get("relationships") or []:
        if not isinstance(relationship, dict):
            continue
        for end_name in ("source", "target"):
            end = relationship.get(end_name)
            if not isinstance(end, dict):
                continue
            endpoint_name = str(end.get("entity") or "").strip()
            if name_policy.preserves_unicode and endpoint_name:
                normalized_endpoint = normalize_structured_name(
                    endpoint_name,
                    style="upper",
                    name_policy=name_policy,
                )
                if isinstance(normalized_endpoint, str):
                    endpoint_name = normalized_endpoint
                    end["entity"] = normalized_endpoint
            endpoint_key = name_policy.comparison_key(endpoint_name)
            if not endpoint_name or endpoint_key in entity_names:
                if endpoint_key in entity_names:
                    end["entity"] = entity_names[endpoint_key]
                continue
            repaired["entities"].append(
                {
                    "name": endpoint_name,
                    "attributes": [{"name": "id", "type": "int"}],
                    "identifier": [{"kind": "attribute", "ref": "id"}],
                    "inherits_from": [],
                }
            )
            entity_names[endpoint_key] = endpoint_name
    return repaired


__all__ = ["add_missing_endpoint_entities"]
