from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_operation_signature_payloads import (
    normalized_operation_signature_payload,
)


def relationship_add_remove_conflict_reason(
    first_sequence: int,
    first_operation: dict[str, Any] | None,
    second_sequence: int,
    second_operation: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str | None:
    first = normalized_operation_signature_payload(first_operation, name_policy=name_policy)
    second = normalized_operation_signature_payload(second_operation, name_policy=name_policy)
    if not first or not second:
        return None
    if {first.get("op"), second.get("op")} != {"addRelationship", "removeRelationship"}:
        return None
    add_payload = first if first.get("op") == "addRelationship" else second
    remove_payload = first if first.get("op") == "removeRelationship" else second
    relationship_name = add_payload.get("name")
    if not relationship_name or not name_policy.names_equal(
        relationship_name,
        remove_payload.get("name"),
    ):
        return None

    add_source = (add_payload.get("source") or {}).get("entity")
    add_target = (add_payload.get("target") or {}).get("entity")
    remove_source = remove_payload.get("source")
    remove_target = remove_payload.get("target")
    if remove_source and remove_target:
        same_relationship = name_policy.names_equal(
            remove_source,
            add_source,
        ) and name_policy.names_equal(remove_target, add_target)
    elif remove_source or remove_target:
        same_relationship = any(
            name_policy.names_equal(remove_source or remove_target, endpoint)
            for endpoint in (add_source, add_target)
        )
    else:
        same_relationship = True
    if not same_relationship:
        return None
    return (
        f"Rejected contradictory relationship operations {first_sequence} and {second_sequence}: "
        f"relationship '{relationship_name}' is both added and removed in the same batch. "
        "Use addRelationship to update multiplicity or role metadata instead."
    )


def deferred_operation_parts(entry: Any) -> tuple[int | None, dict[str, Any] | None, list[str]]:
    if isinstance(entry, tuple) and len(entry) >= 2:
        sequence = entry[0] if isinstance(entry[0], int) else None
        operation = entry[1] if isinstance(entry[1], dict) else None
        return sequence, operation, []
    if isinstance(entry, dict):
        sequence = entry.get("sequence") if isinstance(entry.get("sequence"), int) else None
        operation = entry.get("op") if isinstance(entry.get("op"), dict) else None
        missing_entities = [
            str(entity).strip()
            for entity in (entry.get("missing_entities") or [])
            if str(entity).strip()
        ]
        return sequence, operation, missing_entities
    return None, None, []


def attribute_remove_blocked_by_deferred_relationship_reason(
    remove_sequence: int,
    remove_operation: dict[str, Any] | None,
    deferred_operations: list[Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str | None:
    remove_payload = normalized_operation_signature_payload(
        remove_operation,
        name_policy=name_policy,
    )
    if not remove_payload or remove_payload.get("op") != "removeAttribute":
        return None
    remove_entity = str(remove_payload.get("entity") or "").strip()
    remove_attribute = str(remove_payload.get("name") or "").strip()
    if not remove_entity or not remove_attribute:
        return None

    for deferred_entry in deferred_operations:
        deferred_sequence, deferred_operation, missing_entities = deferred_operation_parts(deferred_entry)
        deferred_payload = normalized_operation_signature_payload(
            deferred_operation,
            name_policy=name_policy,
        )
        if not deferred_payload or deferred_payload.get("op") != "addRelationship":
            continue
        source_entity = str(((deferred_payload.get("source") or {}).get("entity")) or "").strip()
        target_entity = str(((deferred_payload.get("target") or {}).get("entity")) or "").strip()
        if not any(
            name_policy.names_equal(remove_entity, endpoint)
            for endpoint in (source_entity, target_entity)
        ):
            continue
        relationship_name = str(deferred_payload.get("name") or "<unnamed>")
        fallback_missing = [
            entity
            for entity in (source_entity, target_entity)
            if entity and not name_policy.names_equal(entity, remove_entity)
        ]
        missing_text = ", ".join(sorted(set(missing_entities or fallback_missing)))
        if not missing_text:
            missing_text = "unknown endpoint"
        deferred_label = f" {deferred_sequence}" if deferred_sequence is not None else ""
        return (
            f"Rejected removeAttribute operation {remove_sequence} for {remove_entity}.{remove_attribute}: "
            f"same batch still has deferred addRelationship operation{deferred_label} "
            f"'{relationship_name}' touching {remove_entity} with unresolved endpoint(s): {missing_text}. "
            "Apply the replacement entity/relationship first, then retry the attribute removal."
        )
    return None


__all__ = [
    "relationship_add_remove_conflict_reason",
    "deferred_operation_parts",
    "attribute_remove_blocked_by_deferred_relationship_reason",
]
