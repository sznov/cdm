from __future__ import annotations

import hashlib
import json
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_signatures import (
    normalized_operation_signature,
    normalized_operation_signature_payload,
)


def decision_patch_signature(
    patch: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str:
    operation = patch.get("operation") if isinstance(patch, dict) else None
    operation_signature = normalized_operation_signature(operation, name_policy=name_policy)
    if operation_signature:
        return operation_signature
    payload = {
        "kind": patch.get("kind") if isinstance(patch, dict) else "",
        "title": patch.get("title") if isinstance(patch, dict) else "",
        "question": patch.get("question") if isinstance(patch, dict) else "",
        "source": patch.get("source") if isinstance(patch, dict) else "",
    }
    identity_payload = {
        key: name_policy.comparison_key(value)
        for key, value in payload.items()
    }
    return hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def decision_patch_operation_label(
    operation: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str:
    payload = normalized_operation_signature_payload(operation, name_policy=name_policy)
    if not payload:
        return "apply patch"
    op_name = str(payload.get("op") or "")
    if op_name == "setIdentifier":
        entity = str(payload.get("entity") or "").strip()
        relationship_refs = [
            str(part.get("ref") or "").strip()
            for part in (payload.get("parts") or [])
            if isinstance(part, dict)
            and str(part.get("kind") or "").strip() == "relationship"
            and str(part.get("ref") or "").strip()
        ]
        if entity and relationship_refs:
            return f"add {', '.join(relationship_refs)} to {entity} identifier"
        if entity:
            return f"set {entity} identifier"
    if op_name == "addRelationship" and payload.get("name"):
        return f"add relationship {payload['name']}"
    if op_name == "addEntity" and payload.get("name"):
        return f"add entity {payload['name']}"
    return op_name or "apply patch"


__all__ = [
    "decision_patch_operation_label",
    "decision_patch_signature",
]
