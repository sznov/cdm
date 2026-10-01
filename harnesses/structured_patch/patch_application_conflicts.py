from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_signatures import relationship_add_remove_conflict_reason


def relationship_conflict_reason(
    batch_operations: list[tuple[int, dict[str, Any]]],
    sequence: int,
    operation: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str | None:
    for prior_sequence, prior_operation in batch_operations:
        conflict_reason = relationship_add_remove_conflict_reason(
            prior_sequence,
            prior_operation,
            sequence,
            operation,
            name_policy=name_policy,
        )
        if conflict_reason is not None:
            return conflict_reason
    return None


__all__ = ["relationship_conflict_reason"]
