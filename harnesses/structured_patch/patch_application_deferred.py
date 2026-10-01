from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_application_records import (
    deferred_operation_entry,
    operation_applied_payload,
    operation_queued_payload,
)
from harnesses.structured_patch.patch_operation_apply import apply_structured_patch_operation
from harnesses.structured_patch.patch_signatures import normalized_operation_signature
from core.schemas import StructuredModel

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
SnapshotCallback = Callable[[StructuredModel, str, dict[str, Any] | None], Awaitable[None]]


def operation_payload_signature(
    operation: Any,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str:
    if name_policy.preserves_unicode and isinstance(operation, dict):
        normalized_signature = normalized_operation_signature(
            operation,
            name_policy=name_policy,
        )
        if normalized_signature is not None:
            return normalized_signature
    return json.dumps(operation, sort_keys=True, ensure_ascii=False)


def append_deferred_operation_result(
    sequence: int,
    result: dict[str, Any],
    deferred_operations: list[dict[str, Any]],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> None:
    entry = deferred_operation_entry(sequence, result)
    signature = operation_payload_signature(entry.get("op"), name_policy=name_policy)
    if all(
        operation_payload_signature(item.get("op"), name_policy=name_policy) != signature
        for item in deferred_operations
    ):
        deferred_operations.append(entry)


async def queue_deferred_identifier_operation(
    *,
    sequence: int,
    deferred_identifier_operation: dict[str, Any] | None,
    deferred_operations: list[dict[str, Any]],
    emit: EmitCallback,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> None:
    if deferred_identifier_operation is None:
        return
    signature = operation_payload_signature(
        deferred_identifier_operation,
        name_policy=name_policy,
    )
    if any(
        operation_payload_signature(item.get("op"), name_policy=name_policy) == signature
        for item in deferred_operations
    ):
        return
    deferred_operations.append(
        {
            "sequence": sequence,
            "op": deferred_identifier_operation,
            "reason": "Deferred addEntity relationship identifier until referenced relationships exist.",
            "missing_relationships": [
                part["ref"]
                for part in deferred_identifier_operation.get("parts", [])
                if isinstance(part, dict) and part.get("kind") == "relationship"
            ],
        }
    )
    await emit(
        "structured_patch_operation_queued",
        operation_queued_payload(
            sequence,
            deferred_identifier_operation,
            "Queued relationship-based identifier until referenced relationships exist.",
        ),
    )


async def retry_deferred_patch_operations(
    *,
    model: StructuredModel,
    deferred_operations: list[dict[str, Any]],
    applied_operations: list[dict[str, Any]],
    rejected_operations: list[dict[str, Any]],
    already_satisfied_operations: list[dict[str, Any]],
    emit: EmitCallback,
    emit_partial_snapshot: SnapshotCallback,
    deferred_attempt_results: list[dict[str, Any]] | None = None,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> StructuredModel:
    if not deferred_operations:
        return model
    pending = list(deferred_operations)
    deferred_operations.clear()
    remaining: list[dict[str, Any]] = []
    for deferred in pending:
        after, result = apply_structured_patch_operation(
            model,
            deferred["op"],
            name_policy=name_policy,
        )
        result = {**result, "retry_of": deferred.get("sequence"), "deferred_retry": True}
        retry_sequence = deferred.get("retry_sequence")
        if retry_sequence is not None:
            result["sequence"] = retry_sequence
            result["retry_of"] = deferred.get("retry_of", deferred.get("sequence"))
        if result["status"] == "accepted":
            model = after
            applied_operations.append(result)
            await emit(
                "structured_patch_operation_applied",
                operation_applied_payload(
                    status="accepted",
                    result=result,
                    summary=f"Deferred operation applied: {result.get('op', {}).get('op')}.",
                ),
            )
            await emit_partial_snapshot(model, "Deferred operation rendered.", result)
        elif result["status"] == "deferred":
            remaining_entry = {
                key: value
                for key, value in deferred.items()
                if key != "retry_sequence"
            }
            if retry_sequence is not None:
                remaining_entry["last_retry_sequence"] = retry_sequence
                if deferred_attempt_results is not None:
                    deferred_attempt_results.append(result)
                await emit(
                    "structured_patch_operation_applied",
                    operation_applied_payload(
                        status="deferred",
                        result=result,
                        summary=result.get("reason") or "Deferred operation still cannot be applied.",
                    ),
                )
            remaining.append(remaining_entry)
        elif result["status"] == "already_satisfied":
            already_satisfied_operations.append(result)
            await emit(
                "structured_patch_operation_applied",
                operation_applied_payload(
                    status="already_satisfied",
                    result=result,
                    summary=result.get("reason") or "Deferred operation is already satisfied.",
                ),
            )
        else:
            rejected_operations.append(result)
            await emit(
                "structured_patch_operation_applied",
                operation_applied_payload(
                    status="rejected",
                    result=result,
                    summary=result.get("reason") or "Deferred operation rejected.",
                ),
            )
    deferred_operations[:] = remaining
    return model


__all__ = [
    "append_deferred_operation_result",
    "operation_payload_signature",
    "queue_deferred_identifier_operation",
    "retry_deferred_patch_operations",
]
