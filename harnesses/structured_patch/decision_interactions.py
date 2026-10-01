from __future__ import annotations

import hashlib
import json
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.decision_merge import merge_decision_patches
from harnesses.structured_patch.patch_signatures import (
    normalized_operation_signature,
    normalized_operation_signature_payload,
)


def relationship_operation_endpoints(
    operation: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> tuple[str, str] | None:
    payload = normalized_operation_signature_payload(operation, name_policy=name_policy)
    if not payload or payload.get("op") != "addRelationship":
        return None
    source = ((payload.get("source") or {}).get("entity") or "").strip()
    target = ((payload.get("target") or {}).get("entity") or "").strip()
    if not source or not target:
        return None
    return (source, target)


def relationship_operation_unordered_endpoints(
    operation: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> frozenset[str] | None:
    endpoints = relationship_operation_endpoints(operation, name_policy=name_policy)
    if endpoints is None:
        return None
    return frozenset(name_policy.comparison_key(endpoint) for endpoint in endpoints)


def pending_decision_operation_interaction(
    operation: dict[str, Any],
    decision_patches: list[dict[str, Any]],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    operation_signature = normalized_operation_signature(operation, name_policy=name_policy)
    operation_payload = normalized_operation_signature_payload(operation, name_policy=name_policy)
    operation_endpoints = relationship_operation_unordered_endpoints(
        operation,
        name_policy=name_policy,
    )
    for patch in decision_patches or []:
        if not isinstance(patch, dict) or str(patch.get("status") or "pending") != "pending":
            continue
        patch_operation = patch.get("operation")
        if not isinstance(patch_operation, dict):
            continue
        patch_signature = (
            normalized_operation_signature(patch_operation, name_policy=name_policy)
            if name_policy.preserves_unicode
            else patch.get("signature")
            or normalized_operation_signature(patch_operation, name_policy=name_policy)
        )
        if operation_signature and patch_signature == operation_signature:
            return {"kind": "equivalent", "patch": patch}
        patch_payload = normalized_operation_signature_payload(
            patch_operation,
            name_policy=name_policy,
        )
        if not operation_payload or not patch_payload:
            continue
        if operation_payload.get("op") == "addRelationship" and patch_payload.get("op") == "addRelationship":
            patch_endpoints = relationship_operation_unordered_endpoints(
                patch_operation,
                name_policy=name_policy,
            )
            if operation_endpoints and patch_endpoints and operation_endpoints == patch_endpoints:
                return {"kind": "overlap", "patch": patch}
        if operation_payload.get("op") == "setIdentifier" and patch_payload.get("op") == "setIdentifier":
            if operation_payload.get("entity") and name_policy.names_equal(
                operation_payload.get("entity"),
                patch_payload.get("entity"),
            ):
                return {"kind": "overlap", "patch": patch}
    return None


def decision_patch_from_blocked_operation(
    operation: dict[str, Any],
    *,
    blocking_patch: dict[str, Any],
    interaction_kind: str,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any]:
    operation_payload = normalized_operation_signature_payload(
        operation,
        name_policy=name_policy,
    ) or {"op": operation.get("op")}
    target = ""
    if operation_payload.get("op") == "addRelationship":
        source = ((operation_payload.get("source") or {}).get("entity") or "").strip()
        target_entity = ((operation_payload.get("target") or {}).get("entity") or "").strip()
        target = f"{source}-{target_entity}".strip("-")
    elif operation_payload.get("entity"):
        target = str(operation_payload["entity"])
    title = f"Review operation overlapping {blocking_patch.get('title') or blocking_patch.get('id') or 'pending decision'}"
    operation_signature = normalized_operation_signature(operation, name_policy=name_policy)
    if operation_signature is None:
        identity_payload = {
            key: name_policy.comparison_key(value) if isinstance(value, str) else value
            for key, value in operation_payload.items()
        }
        operation_signature = hashlib.sha256(
            json.dumps(identity_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    return {
        "id": f"DP-{operation_signature[:8]}",
        "status": "pending",
        "kind": "overlappingDecision",
        "title": title,
        "question": "Should this patch operation be applied despite overlapping an unresolved decision?",
        "reason": (
            "The patch operation was generated automatically, but it overlaps a pending decision. "
            "It was not applied automatically."
        ),
        "evidence": "",
        "operation": operation,
        "source": "patch_operation_guard",
        "blocked_by": blocking_patch.get("id"),
        "overlap_kind": interaction_kind,
        "target": target,
    }


def mark_equivalent_decision_patches_resolved(
    decision_patches: list[dict[str, Any]],
    operation: dict[str, Any],
    *,
    status: str,
    reason: str,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    operation_signature = normalized_operation_signature(operation, name_policy=name_policy)
    if not operation_signature:
        return decision_patches
    updated: list[dict[str, Any]] = []
    for patch in decision_patches or []:
        if not isinstance(patch, dict):
            continue
        normalized = dict(patch)
        patch_signature = (
            normalized_operation_signature(normalized.get("operation"), name_policy=name_policy)
            if name_policy.preserves_unicode
            else normalized.get("signature")
            or normalized_operation_signature(normalized.get("operation"), name_policy=name_policy)
        )
        if normalized.get("status") == "pending" and patch_signature == operation_signature:
            normalized["status"] = status
            normalized["resolution_reason"] = reason
        updated.append(normalized)
    return merge_decision_patches(updated, name_policy=name_policy)


__all__ = [
    "decision_patch_from_blocked_operation",
    "mark_equivalent_decision_patches_resolved",
    "pending_decision_operation_interaction",
    "relationship_operation_endpoints",
    "relationship_operation_unordered_endpoints",
]
