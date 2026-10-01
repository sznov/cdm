from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.decision_interactions import mark_equivalent_decision_patches_resolved
from harnesses.structured_patch.patch_application_deferred import (
    append_deferred_operation_result,
    queue_deferred_identifier_operation,
)
from harnesses.structured_patch.patch_application_records import (
    accepted_operation_entry,
    accepted_operation_history_record,
    operation_applied_payload,
    rejected_operation_history_record,
)
from harnesses.structured_patch.patch_operation_apply import apply_structured_patch_operation
from harnesses.structured_patch.patch_signatures import (
    split_add_entity_deferred_relationship_identifier,
)
from core.schemas import StructuredModel

EmitCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
SnapshotCallback = Callable[[StructuredModel, str, dict[str, Any] | None], Awaitable[None]]


@dataclass
class ImmediateOperationApplicationResult:
    model: StructuredModel
    decision_patches: list[dict[str, Any]]
    retry_deferred: bool = False


async def apply_immediate_patch_operation(
    *,
    sequence: int,
    operation: dict[str, Any],
    model: StructuredModel,
    decision_patches: list[dict[str, Any]],
    applied_operations: list[dict[str, Any]],
    rejected_operations: list[dict[str, Any]],
    already_satisfied_operations: list[dict[str, Any]],
    deferred_operations: list[dict[str, Any]],
    operation_history: list[dict[str, Any]],
    emit: EmitCallback,
    emit_partial_snapshot: SnapshotCallback,
    preserve_provisional_identifier: bool = False,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> ImmediateOperationApplicationResult:
    operation_to_apply, deferred_identifier_operation = split_add_entity_deferred_relationship_identifier(
        operation,
        preserve_provisional_identifier=preserve_provisional_identifier,
        name_policy=name_policy,
    )
    after, result = apply_structured_patch_operation(
        model,
        operation_to_apply,
        name_policy=name_policy,
    )
    result = {**result, "sequence": sequence}
    status = result["status"]

    async def queue_deferred_identifier() -> None:
        await queue_deferred_identifier_operation(
            sequence=sequence,
            deferred_identifier_operation=deferred_identifier_operation,
            deferred_operations=deferred_operations,
            emit=emit,
            name_policy=name_policy,
        )

    if status == "accepted":
        model = after
        await queue_deferred_identifier()
        decision_patches = mark_equivalent_decision_patches_resolved(
            decision_patches,
            operation,
            status="resolved",
            reason="An equivalent operation was applied to the model.",
            name_policy=name_policy,
        )
        applied_operations.append(result)
        operation_history.append(accepted_operation_history_record(sequence, result))
        await emit(
            "structured_patch_operation_applied",
            operation_applied_payload(
                status="accepted",
                result=result,
                accepted=accepted_operation_entry(result),
                summary=f"Applied structured patch operation {sequence}: {result.get('op', {}).get('op')}.",
            ),
        )
        await emit_partial_snapshot(model, f"Rendered after structured patch operation {sequence}.", result)
        return ImmediateOperationApplicationResult(model=model, decision_patches=decision_patches, retry_deferred=True)

    if status == "deferred":
        append_deferred_operation_result(
            sequence,
            result,
            deferred_operations,
            name_policy=name_policy,
        )
        await emit(
            "structured_patch_operation_applied",
            operation_applied_payload(
                status="deferred",
                result=result,
                summary=f"Deferred structured patch operation {sequence}: {result.get('reason')}.",
            ),
        )
        return ImmediateOperationApplicationResult(model=model, decision_patches=decision_patches)

    if status == "already_satisfied":
        await queue_deferred_identifier()
        decision_patches = mark_equivalent_decision_patches_resolved(
            decision_patches,
            operation,
            status="obsolete",
            reason="The model already satisfied an equivalent pending operation.",
            name_policy=name_policy,
        )
        already_satisfied_operations.append(result)
        await emit(
            "structured_patch_operation_applied",
            operation_applied_payload(
                status="already_satisfied",
                result=result,
                summary=result.get("reason") or f"Structured patch operation {sequence} already satisfied.",
            ),
        )
        return ImmediateOperationApplicationResult(model=model, decision_patches=decision_patches)

    rejected_operations.append(result)
    operation_history.append(rejected_operation_history_record(sequence, result.get("op"), result.get("reason"), result))
    await emit(
        "structured_patch_operation_applied",
        operation_applied_payload(
            status="rejected",
            result=result,
            summary=result.get("reason") or f"Rejected structured patch operation {sequence}.",
        ),
    )
    return ImmediateOperationApplicationResult(model=model, decision_patches=decision_patches)


__all__ = [
    "ImmediateOperationApplicationResult",
    "apply_immediate_patch_operation",
]
