"""Compatibility exports for harness-owned automatic correction policy."""

from harnesses.structured_patch.correction_policy import (
    specification_appears_to_state_identifier,
    stated_identifier_patch_guard_reason,
)


__all__ = [
    "specification_appears_to_state_identifier",
    "stated_identifier_patch_guard_reason",
]
