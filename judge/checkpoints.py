from __future__ import annotations

import re
from typing import Any


CORRECTION_SUMMARY_RE = re.compile(r"\b(correction|posthoc|post-hoc)\b", re.IGNORECASE)
DRAFT_SNAPSHOT_RE = re.compile(r"\b(after[- ]draft|draft)\b", re.IGNORECASE)


def checkpoint_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    try:
        index = int(row.get("snapshot_index") or row.get("snapshot_id") or 0)
    except (TypeError, ValueError):
        index = 0
    return index, str(row.get("snapshot_id") or "")


def is_correction_snapshot(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("summary", "checkpoint_label", "source_stage", "snapshot_id")
    )
    return bool(CORRECTION_SUMMARY_RE.search(text))


def is_draft_snapshot(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("summary", "checkpoint_label", "source_stage", "snapshot_id")
    )
    return bool(DRAFT_SNAPSHOT_RE.search(text))


def checkpoint_row(source: dict[str, Any], label: str, generation_run_id: str, carried_forward: bool) -> dict[str, Any]:
    snapshot_index = source.get("snapshot_index")
    if snapshot_index is None:
        try:
            snapshot_index = int(source.get("snapshot_id") or 0)
        except (TypeError, ValueError):
            snapshot_index = None
    return {
        "spec_id": str(source.get("spec_id") or "").zfill(3),
        "generation_run_id": generation_run_id,
        "checkpoint_label": label,
        "source_snapshot_id": str(source.get("snapshot_id") or ""),
        "source_snapshot_index": snapshot_index,
        "carried_forward": bool(carried_forward),
        "summary": source.get("summary"),
        "model_path": source.get("model_path"),
        "gold_path": source.get("gold_path") or source.get("reference_model_path"),
        "reference_model_path": source.get("reference_model_path") or source.get("gold_path"),
        "spec_path": source.get("spec_path"),
        "eval_dir": source.get("eval_dir"),
        "source_row": source,
    }


def select_protocol_checkpoints(rows: list[dict[str, Any]], generation_run_id: str | None = None) -> list[dict[str, Any]]:
    by_spec_generation: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("status") not in {None, "pending", "generated", "completed"}:
            continue
        if not row.get("model_path"):
            continue
        spec_id = str(row.get("spec_id") or "").zfill(3)
        row_generation_id = str(row.get("generation_run_id") or row.get("generation_id") or generation_run_id or "gen-001")
        if generation_run_id is not None and row_generation_id != generation_run_id:
            continue
        if spec_id:
            by_spec_generation.setdefault((spec_id, row_generation_id), []).append(row)

    selected: list[dict[str, Any]] = []
    for (_spec_id, selected_generation_id), spec_rows in sorted(by_spec_generation.items()):
        ordered = sorted(spec_rows, key=checkpoint_sort_key)
        if not ordered:
            continue
        draft_candidates = [row for row in ordered if is_draft_snapshot(row)]
        first = draft_candidates[0] if draft_candidates else ordered[0]
        correction_candidates = [row for row in ordered if is_correction_snapshot(row)]
        if correction_candidates:
            first_correction_key = checkpoint_sort_key(correction_candidates[0])
            pre_candidates = [
                row
                for row in ordered
                if not is_correction_snapshot(row) and checkpoint_sort_key(row) < first_correction_key
            ]
        else:
            pre_candidates = [row for row in ordered if not is_correction_snapshot(row)]
        pre = pre_candidates[-1] if pre_candidates else ordered[-1]
        selected.append(checkpoint_row(first, "first_valid_draft", selected_generation_id, False))
        selected.append(checkpoint_row(pre, "pre_posthoc", selected_generation_id, False))
        if correction_candidates:
            selected.append(checkpoint_row(correction_candidates[-1], "final_guarded_posthoc", selected_generation_id, False))
    return selected


__all__ = [
    "checkpoint_row",
    "checkpoint_sort_key",
    "is_draft_snapshot",
    "is_correction_snapshot",
    "select_protocol_checkpoints",
]
