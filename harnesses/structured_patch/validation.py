from __future__ import annotations

import json
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.decision_merge import merge_decision_patches
from harnesses.structured_patch.hierarchy_identity_issues import structured_hierarchy_identity_issues
from harnesses.structured_patch.model_issue_decisions import decision_patches_from_structured_model_issues
from harnesses.structured_patch.model_issue_findings import findings_from_structured_model_issues
from harnesses.structured_patch.model_issue_merge import merge_structured_model_issue_lists
from harnesses.structured_patch.patch_signatures import normalized_operation_signature_payload
from core.schemas import StructuredModel


def hard_hierarchy_issue_signature(issue: dict[str, Any]) -> str:
    return json.dumps(
        {
            "kind": issue.get("kind"),
            "target": issue.get("target"),
            "summary": issue.get("summary"),
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def pending_remove_entity_names(
    deferred_operations: list[Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> set[str]:
    names: set[str] = set()
    for entry in deferred_operations:
        operation = entry.get("op") if isinstance(entry, dict) else None
        payload = normalized_operation_signature_payload(
            operation,
            name_policy=name_policy,
        )
        if payload and payload.get("op") == "removeEntity" and payload.get("name"):
            names.add(str(payload["name"]))
    return names


def introduced_hard_hierarchy_issue_reason(
    before_model: StructuredModel,
    after_model: StructuredModel,
    *,
    sequence: int,
    operation: dict[str, Any],
    deferred_operations: list[Any],
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str | None:
    before_keys = {
        hard_hierarchy_issue_signature(issue)
        for issue in structured_hierarchy_identity_issues(before_model)
        if issue.get("kind") == "hardError"
    }
    introduced = [
        issue
        for issue in structured_hierarchy_identity_issues(after_model)
        if issue.get("kind") == "hardError" and hard_hierarchy_issue_signature(issue) not in before_keys
    ]
    pending_deletes = pending_remove_entity_names(
        deferred_operations,
        name_policy=name_policy,
    )
    if pending_deletes:
        introduced = [
            issue
            for issue in introduced
            if not any(
                name_policy.names_equal(
                    str(issue.get("target") or "").split(".", 1)[0],
                    pending_delete,
                )
                for pending_delete in pending_deletes
            )
        ]
    if not introduced:
        return None
    summaries = "; ".join(str(issue.get("summary") or issue.get("target") or "").strip() for issue in introduced[:3])
    if len(introduced) > 3:
        summaries += f"; and {len(introduced) - 3} more"
    op_name = operation.get("op") or operation.get("operation") or "<unknown>"
    return (
        f"Rejected operation {sequence} ({op_name}) because it would introduce "
        f"{len(introduced)} hard hierarchy identity issue(s): {summaries}."
    )


async def run_hierarchy_identity_validation(
    *,
    structured_model: StructuredModel,
    draft_model_issues: list[dict[str, Any]],
    draft_issue_decision_patches: list[dict[str, Any]],
    draft_issue_hard_findings: list[dict[str, str]],
    emit: Any,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]], dict[str, Any]]:
    hierarchy_identity_issues = structured_hierarchy_identity_issues(structured_model)
    hierarchy_identity_decisions = decision_patches_from_structured_model_issues(
        hierarchy_identity_issues,
        name_policy=name_policy,
    )
    hierarchy_identity_findings = findings_from_structured_model_issues(hierarchy_identity_issues)
    if hierarchy_identity_issues:
        draft_model_issues = merge_structured_model_issue_lists(draft_model_issues, hierarchy_identity_issues)
        draft_issue_decision_patches = merge_decision_patches(
            draft_issue_decision_patches,
            hierarchy_identity_decisions,
            name_policy=name_policy,
        )
        draft_issue_hard_findings = [*draft_issue_hard_findings, *hierarchy_identity_findings]
    event_payload = {
        "agent_id": "structuredValidator",
        "accepted": not hierarchy_identity_findings,
        "issues": hierarchy_identity_issues,
        "decision_patches": hierarchy_identity_decisions,
        "hard_findings": hierarchy_identity_findings,
        "summary": (
            "Hierarchy identity check passed."
            if not hierarchy_identity_issues
            else f"Hierarchy identity check produced {len(hierarchy_identity_issues)} issue(s)."
        ),
    }
    await emit("hierarchy_identity_validation", event_payload)
    return draft_model_issues, draft_issue_decision_patches, draft_issue_hard_findings, event_payload


async def run_post_patch_hierarchy_identity_validation(
    *,
    structured_model: StructuredModel,
    decision_patches: list[dict[str, Any]],
    emit: Any,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    post_patch_hierarchy_issues = structured_hierarchy_identity_issues(structured_model)
    post_patch_hierarchy_decisions = decision_patches_from_structured_model_issues(
        post_patch_hierarchy_issues,
        name_policy=name_policy,
    )
    post_patch_hierarchy_findings = findings_from_structured_model_issues(post_patch_hierarchy_issues)
    if post_patch_hierarchy_decisions:
        decision_patches = merge_decision_patches(
            decision_patches,
            post_patch_hierarchy_decisions,
            name_policy=name_policy,
        )
    event_payload = {
        "agent_id": "structuredValidator",
        "stage": "post_patch",
        "accepted": not post_patch_hierarchy_findings,
        "issues": post_patch_hierarchy_issues,
        "decision_patches": post_patch_hierarchy_decisions,
        "hard_findings": post_patch_hierarchy_findings,
        "summary": (
            "Post-patch hierarchy identity check passed."
            if not post_patch_hierarchy_issues
            else f"Post-patch hierarchy identity check produced {len(post_patch_hierarchy_issues)} issue(s)."
        ),
    }
    await emit("hierarchy_identity_validation", event_payload)
    return decision_patches, event_payload


__all__ = [
    "hard_hierarchy_issue_signature",
    "introduced_hard_hierarchy_issue_reason",
    "pending_remove_entity_names",
    "run_hierarchy_identity_validation",
    "run_post_patch_hierarchy_identity_validation",
]
