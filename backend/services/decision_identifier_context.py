from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.schemas import StructuredModel
from harnesses.structured_patch.name_policy import StructuredNamePolicy


def decision_patch_is_identifier_context_addition(patch: dict[str, Any], operation: dict[str, Any]) -> bool:
    if operation.get("op") != "setIdentifier":
        return False
    kind = str(patch.get("kind") or "").strip().lower()
    source = str(patch.get("source") or "").strip().lower()
    sources = {str(item or "").strip().lower() for item in patch.get("sources") or []}
    return (
        kind == "identifiercontext"
        or source == "deterministic_identifier_context_scan"
        or "deterministic_identifier_context_scan" in sources
    )


def merge_identifier_context_operation(
    operation: dict[str, Any],
    model: StructuredModel,
    patch: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy,
) -> tuple[dict[str, Any], bool]:
    """Make identifier-context decisions additive instead of mutually overwriting."""
    if not decision_patch_is_identifier_context_addition(patch, operation):
        return operation, False
    entity_name = str(operation.get("entity") or "").strip()
    if not entity_name:
        return operation, False
    entity = next(
        (item for item in model.entities if name_policy.names_equal(item.name, entity_name)),
        None,
    )
    if entity is None:
        return operation, False
    operation_parts = operation.get("parts") if isinstance(operation.get("parts"), list) else operation.get("identifier")
    if not isinstance(operation_parts, list):
        return operation, False

    current_relationship_parts = [
        {"kind": part.kind, "ref": part.ref}
        for part in entity.identifier
        if part.kind == "relationship"
    ]
    seen: set[tuple[str, str]] = set()
    merged_parts: list[dict[str, str]] = []
    for part in [*current_relationship_parts, *operation_parts]:
        if not isinstance(part, dict):
            continue
        kind = str(part.get("kind") or "").strip()
        ref = str(part.get("ref") or "").strip()
        if kind not in {"attribute", "relationship"} or not ref:
            continue
        key = (kind, name_policy.comparison_key(ref))
        if key in seen:
            continue
        seen.add(key)
        merged_parts.append({"kind": kind, "ref": ref})

    relationship_parts = [part for part in merged_parts if part["kind"] == "relationship"]
    attribute_parts = [part for part in merged_parts if part["kind"] == "attribute"]
    ordered_parts = [*relationship_parts, *attribute_parts]
    if ordered_parts == operation_parts:
        return operation, False
    merged_operation = deepcopy(operation)
    merged_operation["parts"] = ordered_parts
    merged_operation.pop("identifier", None)
    return merged_operation, True


__all__ = ["decision_patch_is_identifier_context_addition", "merge_identifier_context_operation"]
