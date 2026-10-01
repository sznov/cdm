from __future__ import annotations

from copy import deepcopy
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_parse_contract import canonical_structured_patch_op_name
from harnesses.structured_patch.patch_normalization import (
    normalize_structured_attributes_payload,
    normalize_structured_identifier_parts,
    normalize_structured_name,
)


def split_add_entity_deferred_relationship_identifier(
    operation: dict[str, Any],
    *,
    preserve_provisional_identifier: bool = False,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    op_name = canonical_structured_patch_op_name(
        operation.get("op") or operation.get("operation") or operation.get("type")
    )
    if op_name != "addEntity":
        return operation, None
    parts = normalize_structured_identifier_parts(
        operation.get("identifier") or operation.get("parts"),
        name_policy=name_policy,
    )
    if not any(part.get("kind") == "relationship" for part in parts):
        return operation, None
    entity_name = normalize_structured_name(
        operation.get("name") or operation.get("entity"),
        style="upper",
        name_policy=name_policy,
    )
    if not isinstance(entity_name, str) or not entity_name:
        return operation, None
    stripped_operation = deepcopy(operation)
    provisional_identifier: list[dict[str, str]] = []
    if preserve_provisional_identifier:
        provisional_identifier = [
            part for part in parts if part.get("kind") == "attribute"
        ]
        if not provisional_identifier:
            attributes = normalize_structured_attributes_payload(
                operation.get("attributes"),
                name_policy=name_policy,
            )
            if not any(name_policy.names_equal(attribute.get("name"), "id") for attribute in attributes):
                attributes.append({"name": "id", "type": "int"})
            stripped_operation["attributes"] = attributes
            provisional_identifier = [{"kind": "attribute", "ref": "id"}]
    stripped_operation["identifier"] = provisional_identifier
    stripped_operation["parts"] = provisional_identifier
    return stripped_operation, {"op": "setIdentifier", "entity": entity_name, "parts": parts}


__all__ = ["split_add_entity_deferred_relationship_identifier"]
