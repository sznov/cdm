from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_application_records import operation_queued_payload
from harnesses.structured_patch.patch_signatures import normalized_operation_signature_payload

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]

RELATIONSHIP_REMOVAL_QUEUE_SUMMARY = (
    "Queued relationship removal until the patch batch is complete so "
    "remove-and-readd replacement patterns cannot delete relationships."
)
ATTRIBUTE_REMOVAL_QUEUE_SUMMARY = (
    "Queued attribute removal until the patch batch is complete so "
    "replacement entities and relationships can be validated first."
)


async def queue_delayed_removal_if_needed(
    *,
    sequence: int,
    operation: dict[str, Any],
    queued_relationship_removals: list[tuple[int, dict[str, Any]]],
    queued_attribute_removals: list[tuple[int, dict[str, Any]]],
    emit: EmitCallback,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> bool:
    normalized_operation = normalized_operation_signature_payload(
        operation,
        name_policy=name_policy,
    )
    if not normalized_operation:
        return False
    if normalized_operation.get("op") == "removeRelationship":
        queued_relationship_removals.append((sequence, operation))
        await emit(
            "structured_patch_operation_queued",
            operation_queued_payload(sequence, operation, RELATIONSHIP_REMOVAL_QUEUE_SUMMARY),
        )
        return True
    if normalized_operation.get("op") == "removeAttribute":
        queued_attribute_removals.append((sequence, operation))
        await emit(
            "structured_patch_operation_queued",
            operation_queued_payload(sequence, operation, ATTRIBUTE_REMOVAL_QUEUE_SUMMARY),
        )
        return True
    return False


__all__ = [
    "ATTRIBUTE_REMOVAL_QUEUE_SUMMARY",
    "RELATIONSHIP_REMOVAL_QUEUE_SUMMARY",
    "queue_delayed_removal_if_needed",
]
