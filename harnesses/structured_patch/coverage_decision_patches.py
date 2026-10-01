from __future__ import annotations

from typing import Any

from harnesses.structured_patch.patch_parse_contract import (
    STRUCTURED_PATCH_SUPPORTED_OPS,
    canonical_structured_patch_op_name,
    structured_patch_operation_minimal_error,
)


def normalize_decision_patch_payload(item: dict[str, Any], *, index: int) -> dict[str, Any] | None:
    operation = item.get("operation") or item.get("op")
    normalized_operation: dict[str, Any] | None = None
    if operation is not None:
        if not isinstance(operation, dict):
            return None
        normalized_operation = dict(operation)
        normalized_operation["op"] = canonical_structured_patch_op_name(
            normalized_operation.get("op") or normalized_operation.get("operation") or normalized_operation.get("type")
        )
        if normalized_operation["op"] not in STRUCTURED_PATCH_SUPPORTED_OPS:
            return None
        if structured_patch_operation_minimal_error(normalized_operation):
            return None
    patch_id = str(item.get("id") or f"DP{index}").strip() or f"DP{index}"
    title = str(item.get("title") or item.get("summary") or f"Decision patch {index}").strip()
    question = str(item.get("question") or item.get("prompt") or title).strip()
    return {
        "id": patch_id,
        "status": str(item.get("status") or "pending").strip() or "pending",
        "title": title,
        "question": question,
        "kind": str(item.get("kind") or "modelingDecision").strip() or "modelingDecision",
        "reason": str(item.get("reason") or item.get("justification") or "").strip(),
        "evidence": str(item.get("evidence") or "").strip(),
        "operation": normalized_operation,
        "source": str(item.get("source") or "coverage_critic").strip() or "coverage_critic",
    }


__all__ = ["normalize_decision_patch_payload"]
