from __future__ import annotations

from typing import Any

from harnesses.structured_patch.patch_parse_contract import (
    canonical_structured_patch_op_name,
    structured_patch_operation_minimal_error,
)


def structured_patch_operations_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("operation"), dict):
            payload = payload["operation"]
        elif isinstance(payload.get("operations"), list):
            return structured_patch_operations_from_payload(payload["operations"])
        elif isinstance(payload.get("ops"), list):
            return structured_patch_operations_from_payload(payload["ops"])
        op = dict(payload)
        op["op"] = canonical_structured_patch_op_name(op.get("op") or op.get("operation") or op.get("type"))
        if structured_patch_operation_minimal_error(op):
            return []
        return [op]
    if isinstance(payload, list):
        operations: list[dict[str, Any]] = []
        for item in payload:
            operations.extend(structured_patch_operations_from_payload(item))
        return operations
    return []


__all__ = ["structured_patch_operations_from_payload"]
