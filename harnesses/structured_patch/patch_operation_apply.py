from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_parse_contract import (
    STRUCTURED_PATCH_SUPPORTED_OPS,
    canonical_structured_patch_op_name,
)
from harnesses.structured_patch.patch_attribute_operations import apply_attribute_patch_operation
from harnesses.structured_patch.patch_deltas import summarize_structured_model_delta
from harnesses.structured_patch.patch_entity_operations import apply_entity_patch_operation
from harnesses.structured_patch.patch_identifier_operations import apply_identifier_patch_operation
from harnesses.structured_patch.patch_inheritance_operations import apply_inheritance_patch_operation
from harnesses.structured_patch.patch_normalization import (
    remove_unused_fallback_id_attributes,
    repair_relationship_identified_association_multiplicities_payload,
    validate_structured_patch_payload,
)
from harnesses.structured_patch.patch_relationship_operations import apply_relationship_patch_operation
from harnesses.structured_patch.patch_rename_operations import apply_rename_patch_operation
from core.schemas import StructuredModel, StructuredOutputError


ENTITY_OPS = {"addEntity", "removeEntity"}
ATTRIBUTE_OPS = {"addAttribute", "removeAttribute"}
RELATIONSHIP_OPS = {"addRelationship", "removeRelationship"}
INHERITANCE_OPS = {"addInheritance", "removeInheritance"}
RENAME_OPS = {"renameEntity", "renameAttribute", "renameRelationship"}


def apply_structured_patch_operation(
    model: StructuredModel,
    operation: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> tuple[StructuredModel, dict[str, Any]]:
    op = dict(operation or {})
    op_name = canonical_structured_patch_op_name(op.get("op") or op.get("operation") or op.get("type"))
    op["op"] = op_name
    if op_name not in STRUCTURED_PATCH_SUPPORTED_OPS:
        return model, {"status": "rejected", "op": op, "reason": f"Unsupported structured patch op '{op_name or '<missing>'}'."}

    payload = model.model_dump(mode="json")
    before_payload = deepcopy(payload)
    deterministic_repairs: list[dict[str, Any]] = []

    try:
        early_result = _apply_patch_operation_payload(
            payload,
            op_name,
            op,
            deterministic_repairs,
            name_policy=name_policy,
        )
        if early_result is not None:
            return model, early_result
    except (StructuredOutputError, ValidationError, ValueError) as exc:
        return model, {"status": "rejected", "op": op, "reason": str(exc)}

    remove_unused_fallback_id_attributes(payload)
    deterministic_repairs.extend(repair_relationship_identified_association_multiplicities_payload(payload))

    if payload == before_payload:
        return model, {"status": "already_satisfied", "op": op, "reason": "Operation made no structural change."}
    try:
        after_model = validate_structured_patch_payload(payload)
        name_policy.validate_model_names(after_model)
    except (StructuredOutputError, ValidationError, ValueError) as exc:
        return model, {"status": "rejected", "op": op, "reason": str(exc)}
    return after_model, {
        "status": "accepted",
        "op": op,
        "delta": summarize_structured_model_delta(model, after_model),
        "reason": "Operation applied.",
        "deterministic_repairs": deterministic_repairs,
    }


def _apply_patch_operation_payload(
    payload: dict[str, Any],
    op_name: str,
    op: dict[str, Any],
    deterministic_repairs: list[dict[str, Any]],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    if op_name in ENTITY_OPS:
        return apply_entity_patch_operation(payload, op_name, op, name_policy=name_policy)
    if op_name in ATTRIBUTE_OPS:
        return apply_attribute_patch_operation(payload, op_name, op, name_policy=name_policy)
    if op_name in RELATIONSHIP_OPS:
        return apply_relationship_patch_operation(payload, op_name, op, name_policy=name_policy)
    if op_name == "setIdentifier":
        return apply_identifier_patch_operation(
            payload,
            op,
            deterministic_repairs,
            name_policy=name_policy,
        )
    if op_name in INHERITANCE_OPS:
        return apply_inheritance_patch_operation(payload, op_name, op, name_policy=name_policy)
    if op_name in RENAME_OPS:
        return apply_rename_patch_operation(payload, op_name, op, name_policy=name_policy)
    raise StructuredOutputError(f"Unsupported structured patch op '{op_name or '<missing>'}'.")


__all__ = ["apply_structured_patch_operation"]
