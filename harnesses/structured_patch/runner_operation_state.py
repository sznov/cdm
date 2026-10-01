from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harnesses.structured_patch.run_resume import ASYNC_OP_PATCH_RESUME_STAGES


@dataclass(slots=True)
class AsyncOpPatchOperationState:
    applied_operations: list[dict[str, Any]] = field(default_factory=list)
    rejected_operations: list[dict[str, Any]] = field(default_factory=list)
    already_satisfied_operations: list[dict[str, Any]] = field(default_factory=list)
    deferred_operations: list[dict[str, Any]] = field(default_factory=list)


def _dict_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [item for item in payload.get(key, []) if isinstance(item, dict)]


def operation_state_from_resume_payload(
    *,
    resume_payload: dict[str, Any],
    resume_order: int,
) -> AsyncOpPatchOperationState:
    if resume_order < ASYNC_OP_PATCH_RESUME_STAGES["async-op-patch-after-patch-operations"]:
        return AsyncOpPatchOperationState()
    return AsyncOpPatchOperationState(
        applied_operations=_dict_list(resume_payload, "applied_operations"),
        rejected_operations=_dict_list(resume_payload, "rejected_operations"),
        already_satisfied_operations=_dict_list(resume_payload, "already_satisfied_operations"),
        deferred_operations=_dict_list(resume_payload, "deferred_operations"),
    )


__all__ = ["AsyncOpPatchOperationState", "operation_state_from_resume_payload"]
