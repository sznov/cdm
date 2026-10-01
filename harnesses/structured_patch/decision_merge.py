from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.decision_options import ensure_decision_patch_options
from harnesses.structured_patch.decision_signatures import decision_patch_signature


def merge_decision_patch_metadata(
    target: dict[str, Any],
    incoming: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> None:
    sources = {
        source
        for source in [
            target.get("source"),
            incoming.get("source"),
            *(target.get("sources") or [] if isinstance(target.get("sources"), list) else []),
            *(incoming.get("sources") or [] if isinstance(incoming.get("sources"), list) else []),
        ]
        if isinstance(source, str) and source.strip()
    }
    if sources:
        target["sources"] = sorted(sources)
    titles = {
        title
        for title in [
            target.get("title"),
            incoming.get("title"),
            *(target.get("merged_titles") or [] if isinstance(target.get("merged_titles"), list) else []),
            *(incoming.get("merged_titles") or [] if isinstance(incoming.get("merged_titles"), list) else []),
        ]
        if isinstance(title, str) and title.strip()
    }
    if len(titles) > 1:
        target["merged_titles"] = sorted(titles)
    if not target.get("reason") and incoming.get("reason"):
        target["reason"] = incoming["reason"]
    if not target.get("evidence") and incoming.get("evidence"):
        target["evidence"] = incoming["evidence"]
    if not target.get("apply_label") and incoming.get("apply_label"):
        target["apply_label"] = incoming["apply_label"]
    if isinstance(incoming.get("options"), list):
        if not isinstance(target.get("options"), list) or not target.get("options"):
            target["options"] = incoming["options"]
        else:
            existing_ids = {
                str(option.get("id") or option.get("label") or "").strip().lower()
                for option in target["options"]
                if isinstance(option, dict)
            }
            for option in incoming["options"]:
                if not isinstance(option, dict):
                    continue
                key = str(option.get("id") or option.get("label") or "").strip().lower()
                if key and key not in existing_ids:
                    target["options"].append(option)
                    existing_ids.add(key)
    ensure_decision_patch_options(target, name_policy=name_policy)


_DECISION_STATE_FIELDS = (
    "resolution_reason",
    "applied_at_utc",
    "noted_at_utc",
    "rejected_at_utc",
    "selected_option_id",
    "selected_option_label",
    "selected_option_text",
    "applied_result",
)


def merge_decision_patches(
    *patch_groups: list[dict[str, Any]],
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_signature: dict[str, dict[str, Any]] = {}
    for group in patch_groups:
        for patch in group or []:
            if not isinstance(patch, dict):
                continue
            signature = decision_patch_signature(patch, name_policy=name_policy)
            if signature in by_signature:
                merge_decision_patch_metadata(
                    by_signature[signature],
                    patch,
                    name_policy=name_policy,
                )
                continue
            normalized = dict(patch)
            normalized.setdefault("id", f"DP{len(merged) + 1}")
            normalized.setdefault("status", "pending")
            normalized["signature"] = signature
            ensure_decision_patch_options(normalized, name_policy=name_policy)
            by_signature[signature] = normalized
            merged.append(normalized)
    for index, patch in enumerate(merged, start=1):
        ensure_decision_patch_options(patch, name_policy=name_policy)
        patch["id"] = str(patch.get("id") or f"DP-{patch['signature'][:8]}").strip() or f"DP{index}"
    seen_ids: set[str] = set()
    for index, patch in enumerate(merged, start=1):
        patch_id = str(patch.get("id") or "").strip()
        if not patch_id or patch_id in seen_ids:
            patch_id = f"DP-{patch['signature'][:8]}"
        if patch_id in seen_ids:
            patch_id = f"DP{index}"
        patch["id"] = patch_id
        seen_ids.add(patch_id)
    return merged


def merge_decision_patches_latest_state(
    *patch_groups: list[dict[str, Any]],
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    """Canonicalize persisted/refined decisions without changing legacy merge semantics."""

    merged = merge_decision_patches(*patch_groups, name_policy=name_policy)
    by_signature = {str(patch.get("signature") or ""): patch for patch in merged}
    for group in patch_groups:
        for incoming in group or []:
            if not isinstance(incoming, dict):
                continue
            target = by_signature.get(
                decision_patch_signature(incoming, name_policy=name_policy)
            )
            if target is None:
                continue
            incoming_status = str(incoming.get("status") or "").strip().lower()
            target_status = str(target.get("status") or "pending").strip().lower()
            # A repeated pending proposal cannot reopen terminal/resolved state;
            # later explicit non-pending state is authoritative.
            if not incoming_status or (incoming_status == "pending" and target_status != "pending"):
                continue
            target["status"] = incoming["status"]
            for field in _DECISION_STATE_FIELDS:
                if field in incoming:
                    target[field] = incoming[field]
    return merged


__all__ = [
    "merge_decision_patch_metadata",
    "merge_decision_patches",
    "merge_decision_patches_latest_state",
]
