from __future__ import annotations

from datetime import datetime
import json
import re
from pathlib import Path
from typing import Any

from core.artifacts import load_json


CORRECTION_RE = re.compile(r"\b(correction|posthoc|post-hoc)\b", re.IGNORECASE)


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    try:
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _seconds_between(start: Any, end: Any) -> float | None:
    start_dt = _parse_utc(start)
    end_dt = _parse_utc(end)
    if start_dt is None or end_dt is None:
        return None
    return max((end_dt - start_dt).total_seconds(), 0.0)


def _load_json_if_exists(path: Path | str | None) -> Any:
    if not path:
        return None
    candidate = Path(str(path))
    if not candidate.exists():
        return None
    try:
        return load_json(candidate)
    except (OSError, json.JSONDecodeError):
        return None


def _timing_key(row: dict[str, Any]) -> str:
    return f"{row.get('generation_run_id') or row.get('generation_id')}-{str(row.get('spec_id') or '').zfill(3)}"


def _timing_index(run_root: Path) -> dict[str, dict[str, Any]]:
    payload = _load_json_if_exists(run_root / "run_timing.json")
    if not isinstance(payload, list):
        return {}
    output: dict[str, dict[str, Any]] = {}
    for row in payload:
        if isinstance(row, dict) and row.get("key"):
            output[str(row["key"])] = row
    return output


def _checkpoint_timestamp(row: dict[str, Any], timing: dict[str, Any] | None) -> str:
    checkpoint = _load_json_if_exists(row.get("source_checkpoint_path"))
    if isinstance(checkpoint, dict) and checkpoint.get("timestamp_utc"):
        return str(checkpoint["timestamp_utc"])
    if row.get("source_result_path") and timing and timing.get("ended_at_utc"):
        return str(timing["ended_at_utc"])
    return ""


def _is_correction(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("summary", "checkpoint_label", "source_stage", "snapshot_id")
    )
    return bool(CORRECTION_RE.search(text))


def enrich_structured_patch_snapshot_rows(rows: list[dict[str, Any]], run_root: Path) -> list[dict[str, Any]]:
    """Add neutral trajectory metadata to structured-patch snapshot rows.

    Existing snapshot fields are preserved. The added fields are intentionally
    generic so judge/reporting code can consume them without importing the
    structured-patch harness.
    """

    timing_by_key = _timing_index(run_root)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("spec_id") or "").zfill(3), str(row.get("generation_run_id") or row.get("generation_id") or ""))
        grouped.setdefault(key, []).append(row)

    enriched: list[dict[str, Any]] = []
    for _key, group_rows in sorted(grouped.items()):
        ordered = sorted(group_rows, key=lambda item: int(item.get("snapshot_index") or 0))
        previous_snapshot_id = ""
        correction_index = 0
        for row in ordered:
            current = dict(row)
            timing = timing_by_key.get(_timing_key(current), {})
            timestamp = _checkpoint_timestamp(current, timing)
            started_at = str(timing.get("started_at_utc") or "")
            cumulative = _seconds_between(started_at, timestamp)
            is_correction = _is_correction(current)
            if is_correction:
                correction_index += 1
            current.update(
                {
                    "run_started_at_utc": started_at,
                    "checkpoint_timestamp_utc": timestamp,
                    "cumulative_seconds": round(cumulative, 3) if cumulative is not None else "",
                    "cumulative_minutes": round(cumulative / 60, 6) if cumulative is not None else "",
                    "previous_snapshot_id": previous_snapshot_id,
                    "parent_snapshot_id": previous_snapshot_id,
                    "is_correction_step": is_correction,
                    "correction_step_index": correction_index if is_correction else "",
                }
            )
            previous_snapshot_id = str(current.get("snapshot_id") or "")
            enriched.append(current)
    return enriched


__all__ = ["enrich_structured_patch_snapshot_rows"]
