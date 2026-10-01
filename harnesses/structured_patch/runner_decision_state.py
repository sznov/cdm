from __future__ import annotations

import json
from typing import Any

from harnesses.structured_patch.decision_identifier_context import propose_identifier_context_decision_patches
from harnesses.structured_patch.decision_merge import merge_decision_patches
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.run_resume import ASYNC_OP_PATCH_RESUME_STAGES
from core.schemas import StructuredModel


def decision_seed_patches_from_resume_or_draft(
    *,
    resume_payload: dict[str, Any],
    resume_order: int,
    draft_issue_decision_patches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if resume_order < ASYNC_OP_PATCH_RESUME_STAGES["async-op-patch-after-coverage-critic"]:
        return draft_issue_decision_patches
    resume_decisions = resume_payload.get("decision_patches")
    if not isinstance(resume_decisions, list):
        return draft_issue_decision_patches
    return [item for item in resume_decisions if isinstance(item, dict)]


def merged_decision_patches_from_resume_or_draft(
    *,
    resume_payload: dict[str, Any],
    resume_order: int,
    draft_issue_decision_patches: list[dict[str, Any]],
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    return merge_decision_patches(
        decision_seed_patches_from_resume_or_draft(
            resume_payload=resume_payload,
            resume_order=resume_order,
            draft_issue_decision_patches=draft_issue_decision_patches,
        ),
        name_policy=name_policy,
    )


def _canonical_decision_payload(patches: list[dict[str, Any]]) -> str:
    return json.dumps(patches, sort_keys=True, ensure_ascii=False)


def rescan_identifier_context_decisions(
    *,
    decision_patches: list[dict[str, Any]],
    structured_model: StructuredModel,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> tuple[list[dict[str, Any]], bool]:
    rescanned_decision_patches = merge_decision_patches(
        decision_patches,
        propose_identifier_context_decision_patches(
            structured_model,
            name_policy=name_policy,
        ),
        name_policy=name_policy,
    )
    changed = _canonical_decision_payload(rescanned_decision_patches) != _canonical_decision_payload(decision_patches)
    return rescanned_decision_patches, changed


__all__ = [
    "decision_seed_patches_from_resume_or_draft",
    "merged_decision_patches_from_resume_or_draft",
    "rescan_identifier_context_decisions",
]
