from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from core.artifacts import load_json, write_csv, write_json
from judge.repeated import percentile, round4


TRAJECTORY_FIELDS = [
    "spec_id",
    "generation_run_id",
    "snapshot_id",
    "snapshot_index",
    "checkpoint_label",
    "source_stage",
    "summary",
    "is_correction_step",
    "correction_step_index",
    "previous_snapshot_id",
    "parent_snapshot_id",
    "run_started_at_utc",
    "checkpoint_timestamp_utc",
    "cumulative_seconds",
    "cumulative_minutes",
    "precision",
    "recall",
    "f1",
    "macro_f1",
]

TIMING_SUMMARY_FIELDS = [
    "checkpoint_label",
    "source_stage",
    "count",
    "seconds_mean",
    "seconds_median",
    "seconds_p10",
    "seconds_p90",
    "seconds_min",
    "seconds_max",
    "minutes_mean",
    "minutes_median",
    "minutes_p10",
    "minutes_p90",
    "minutes_min",
    "minutes_max",
]

BEST_CHECKPOINT_FIELDS = [
    "summary_kind",
    "spec_id",
    "generation_run_id",
    "snapshot_id",
    "snapshot_index",
    "checkpoint_label",
    "source_stage",
    "f1",
    "macro_f1",
    "precision",
    "recall",
]

DELTA_FIELDS = [
    "spec_id",
    "generation_run_id",
    "comparison",
    "left_snapshot_id",
    "right_snapshot_id",
    "left_checkpoint_label",
    "right_checkpoint_label",
    "precision_delta",
    "recall_delta",
    "f1_delta",
    "macro_f1_delta",
]

CORRECTION_PROGRESS_FIELDS = [
    "spec_id",
    "generation_run_id",
    "correction_step_index",
    "snapshot_id",
    "checkpoint_label",
    "source_stage",
    "previous_snapshot_id",
    "pre_posthoc_snapshot_id",
    "precision",
    "recall",
    "f1",
    "macro_f1",
    "precision_delta_vs_previous",
    "recall_delta_vs_previous",
    "f1_delta_vs_previous",
    "macro_f1_delta_vs_previous",
    "precision_delta_vs_pre_posthoc",
    "recall_delta_vs_pre_posthoc",
    "f1_delta_vs_pre_posthoc",
    "macro_f1_delta_vs_pre_posthoc",
]

CORRECTION_SUMMARY_FIELDS = [
    "correction_step_index",
    "count",
    "mean_precision",
    "mean_recall",
    "mean_f1",
    "mean_macro_f1",
    "median_f1",
    "mean_f1_delta_vs_previous",
    "mean_f1_delta_vs_pre_posthoc",
]

METRICS = ("precision", "recall", "f1", "macro_f1")


def _as_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _mean(values: list[float]) -> float | str:
    return round4(statistics.mean(values)) if values else ""


def _median(values: list[float]) -> float | str:
    return round4(statistics.median(values)) if values else ""


def _pct(values: list[float], pct: float) -> float | str:
    value = percentile(values, pct)
    return round4(value) if value is not None else ""


def _score_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("spec_id") or "").zfill(3),
        str(row.get("generation_run_id") or row.get("generation_id") or ""),
        str(row.get("source_snapshot_id") or row.get("checkpoint_label") or ""),
    )


def _snapshot_score_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("spec_id") or "").zfill(3),
        str(row.get("generation_run_id") or row.get("generation_id") or ""),
        str(row.get("snapshot_id") or ""),
    )


def score_index(majority_rows: list[dict[str, Any]] | None) -> dict[tuple[str, str, str], dict[str, Any]]:
    output: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in majority_rows or []:
        if isinstance(row, dict):
            output[_score_key(row)] = row
    return output


def trajectory_rows(snapshot_rows: list[dict[str, Any]], majority_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    scores = score_index(majority_rows)
    rows: list[dict[str, Any]] = []
    for row in snapshot_rows:
        if not isinstance(row, dict):
            continue
        current = dict(row)
        score = scores.get(_snapshot_score_key(current), {})
        for metric in METRICS:
            current[metric] = score.get(metric, "")
        rows.append(current)
    rows.sort(key=lambda item: (str(item.get("spec_id") or ""), str(item.get("generation_run_id") or ""), _as_int(item.get("snapshot_index"))))
    return rows


def checkpoint_timing_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        seconds = _as_float(row.get("cumulative_seconds"))
        if seconds is None:
            continue
        grouped.setdefault((str(row.get("checkpoint_label") or ""), str(row.get("source_stage") or "")), []).append(seconds)
    output: list[dict[str, Any]] = []
    for (checkpoint_label, source_stage), values in sorted(grouped.items()):
        minutes = [value / 60 for value in values]
        output.append(
            {
                "checkpoint_label": checkpoint_label,
                "source_stage": source_stage,
                "count": len(values),
                "seconds_mean": _mean(values),
                "seconds_median": _median(values),
                "seconds_p10": _pct(values, 0.10),
                "seconds_p90": _pct(values, 0.90),
                "seconds_min": round4(min(values)),
                "seconds_max": round4(max(values)),
                "minutes_mean": _mean(minutes),
                "minutes_median": _median(minutes),
                "minutes_p10": _pct(minutes, 0.10),
                "minutes_p90": _pct(minutes, 0.90),
                "minutes_min": round4(min(minutes)),
                "minutes_max": round4(max(minutes)),
            }
        )
    return output


def _group_by_generation(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("spec_id") or "").zfill(3), str(row.get("generation_run_id") or row.get("generation_id") or ""))
        grouped.setdefault(key, []).append(row)
    return grouped


def best_checkpoint_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for (spec_id, generation_id), group_rows in sorted(_group_by_generation(rows).items()):
        scored = [row for row in group_rows if _as_float(row.get("f1")) is not None]
        if not scored:
            continue
        best = sorted(scored, key=lambda row: (-float(row["f1"]), _as_int(row.get("snapshot_index"))))[0]
        output.append(
            {
                "summary_kind": "diagnostic_oracle_best_checkpoint",
                "spec_id": spec_id,
                "generation_run_id": generation_id,
                "snapshot_id": best.get("snapshot_id", ""),
                "snapshot_index": best.get("snapshot_index", ""),
                "checkpoint_label": best.get("checkpoint_label", ""),
                "source_stage": best.get("source_stage", ""),
                "f1": best.get("f1", ""),
                "macro_f1": best.get("macro_f1", ""),
                "precision": best.get("precision", ""),
                "recall": best.get("recall", ""),
            }
        )
    return output


def _metric_delta(left: dict[str, Any] | None, right: dict[str, Any] | None, metric: str) -> float | str:
    if left is None or right is None:
        return ""
    left_value = _as_float(left.get(metric))
    right_value = _as_float(right.get(metric))
    if left_value is None or right_value is None:
        return ""
    return round4(right_value - left_value)


def _delta_row(comparison: str, left: dict[str, Any] | None, right: dict[str, Any] | None, spec_id: str, generation_id: str) -> dict[str, Any]:
    row = {
        "spec_id": spec_id,
        "generation_run_id": generation_id,
        "comparison": comparison,
        "left_snapshot_id": left.get("snapshot_id", "") if left else "",
        "right_snapshot_id": right.get("snapshot_id", "") if right else "",
        "left_checkpoint_label": left.get("checkpoint_label", "") if left else "",
        "right_checkpoint_label": right.get("checkpoint_label", "") if right else "",
    }
    for metric in METRICS:
        row[f"{metric}_delta"] = _metric_delta(left, right, metric)
    return row


def checkpoint_delta_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for (spec_id, generation_id), group_rows in sorted(_group_by_generation(rows).items()):
        ordered = sorted(group_rows, key=lambda row: _as_int(row.get("snapshot_index")))
        if not ordered:
            continue
        first = ordered[0]
        correction_rows = [row for row in ordered if row.get("is_correction_step") is True]
        if correction_rows:
            first_correction_index = _as_int(correction_rows[0].get("snapshot_index"))
            pre_candidates = [row for row in ordered if row.get("is_correction_step") is not True and _as_int(row.get("snapshot_index")) < first_correction_index]
        else:
            pre_candidates = [row for row in ordered if row.get("is_correction_step") is not True]
        pre_posthoc = pre_candidates[-1] if pre_candidates else None
        final = ordered[-1]
        scored = [row for row in ordered if _as_float(row.get("f1")) is not None]
        best = sorted(scored, key=lambda row: (-float(row["f1"]), _as_int(row.get("snapshot_index"))))[0] if scored else None
        output.append(_delta_row("first_to_final", first, final, spec_id, generation_id))
        output.append(_delta_row("pre_posthoc_to_final", pre_posthoc, final, spec_id, generation_id))
        output.append(_delta_row("final_to_oracle_best", final, best, spec_id, generation_id))
    return output


def correction_progression_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for (spec_id, generation_id), group_rows in sorted(_group_by_generation(rows).items()):
        ordered = sorted(group_rows, key=lambda row: _as_int(row.get("snapshot_index")))
        correction_rows = [row for row in ordered if row.get("is_correction_step") is True]
        if not correction_rows:
            continue
        first_correction_index = _as_int(correction_rows[0].get("snapshot_index"))
        pre_candidates = [row for row in ordered if row.get("is_correction_step") is not True and _as_int(row.get("snapshot_index")) < first_correction_index]
        pre_posthoc = pre_candidates[-1] if pre_candidates else None
        by_snapshot = {str(row.get("snapshot_id") or ""): row for row in ordered}
        for correction in correction_rows:
            previous = by_snapshot.get(str(correction.get("previous_snapshot_id") or ""))
            row = {
                "spec_id": spec_id,
                "generation_run_id": generation_id,
                "correction_step_index": correction.get("correction_step_index", ""),
                "snapshot_id": correction.get("snapshot_id", ""),
                "checkpoint_label": correction.get("checkpoint_label", ""),
                "source_stage": correction.get("source_stage", ""),
                "previous_snapshot_id": correction.get("previous_snapshot_id", ""),
                "pre_posthoc_snapshot_id": pre_posthoc.get("snapshot_id", "") if pre_posthoc else "",
            }
            for metric in METRICS:
                row[metric] = correction.get(metric, "")
                row[f"{metric}_delta_vs_previous"] = _metric_delta(previous, correction, metric)
                row[f"{metric}_delta_vs_pre_posthoc"] = _metric_delta(pre_posthoc, correction, metric)
            output.append(row)
    return output


def correction_progression_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("correction_step_index") or ""), []).append(row)
    output: list[dict[str, Any]] = []
    for step_index, step_rows in sorted(grouped.items(), key=lambda item: _as_int(item[0])):
        row: dict[str, Any] = {"correction_step_index": step_index, "count": len(step_rows)}
        for metric in METRICS:
            values = [_as_float(item.get(metric)) for item in step_rows]
            row[f"mean_{metric}"] = _mean([value for value in values if value is not None])
        f1_values = [_as_float(item.get("f1")) for item in step_rows]
        row["median_f1"] = _median([value for value in f1_values if value is not None])
        previous_delta_values = [_as_float(item.get("f1_delta_vs_previous")) for item in step_rows]
        pre_delta_values = [_as_float(item.get("f1_delta_vs_pre_posthoc")) for item in step_rows]
        row["mean_f1_delta_vs_previous"] = _mean([value for value in previous_delta_values if value is not None])
        row["mean_f1_delta_vs_pre_posthoc"] = _mean([value for value in pre_delta_values if value is not None])
        output.append(row)
    return output


def build_trajectory_reports(
    snapshot_rows: list[dict[str, Any]],
    majority_rows: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    rows = trajectory_rows(snapshot_rows, majority_rows)
    correction_rows = correction_progression_rows(rows)
    return {
        "trajectory_rows": rows,
        "checkpoint_timing_summary": checkpoint_timing_summary(rows),
        "best_checkpoint_rows": best_checkpoint_rows(rows),
        "checkpoint_delta_rows": checkpoint_delta_rows(rows),
        "correction_progression_rows": correction_rows,
        "correction_progression_summary": correction_progression_summary(correction_rows),
    }


def write_trajectory_reports(out_dir: Path, reports: dict[str, list[dict[str, Any]]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fields_by_name = {
        "trajectory_rows": TRAJECTORY_FIELDS,
        "checkpoint_timing_summary": TIMING_SUMMARY_FIELDS,
        "best_checkpoint_rows": BEST_CHECKPOINT_FIELDS,
        "checkpoint_delta_rows": DELTA_FIELDS,
        "correction_progression_rows": CORRECTION_PROGRESS_FIELDS,
        "correction_progression_summary": CORRECTION_SUMMARY_FIELDS,
    }
    for name, rows in reports.items():
        write_json(out_dir / f"{name}.json", rows)
        write_csv(out_dir / f"{name}.csv", rows, fields_by_name[name])


def load_optional_rows(path: Path | None) -> list[dict[str, Any]] | None:
    if path is None or not path.exists():
        return None
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON list: {path}")
    return [row for row in payload if isinstance(row, dict)]


__all__ = [
    "build_trajectory_reports",
    "checkpoint_delta_rows",
    "checkpoint_timing_summary",
    "correction_progression_rows",
    "correction_progression_summary",
    "best_checkpoint_rows",
    "load_optional_rows",
    "trajectory_rows",
    "write_trajectory_reports",
]
