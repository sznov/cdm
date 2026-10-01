from __future__ import annotations

import statistics
import re
from pathlib import Path
from typing import Any

from core.artifacts import (
    load_json,
    read_checkpoint_manifest,
    write_canonical_run_manifest,
    write_csv,
    write_json,
)


KINDS = {
    "overall": None,
    "entity": "entities",
    "attribute": "attributes",
    "relationship": "relationships",
    "identifier": "identifiers",
}


def _counts(row: dict[str, Any], kind: str) -> dict[str, Any]:
    json_kind = KINDS[kind]
    if json_kind is None:
        return row
    return (row.get("by_kind") or {}).get(json_kind) or {}


def _ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def summarize_profile(
    profile: str,
    rows: list[dict[str, Any]],
    reliability: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    reliability = reliability or []
    output: list[dict[str, Any]] = []
    rel_precision = [float(row["precision_sd"]) for row in reliability if row.get("precision_sd") not in (None, "")]
    rel_recall = [float(row["recall_sd"]) for row in reliability if row.get("recall_sd") not in (None, "")]
    for kind in KINDS:
        gold = sum(int(_counts(row, kind).get("gold_count") or 0) for row in rows)
        predicted = sum(int(_counts(row, kind).get("predicted_count") or 0) for row in rows)
        represented = sum(int(_counts(row, kind).get("represented_gold_count") or 0) for row in rows)
        supported = sum(int(_counts(row, kind).get("supported_predicted_count") or 0) for row in rows)
        row_recalls = [
            _ratio(float(_counts(row, kind).get("represented_gold_count") or 0), float(_counts(row, kind).get("gold_count") or 0))
            for row in rows
        ]
        row_precisions = [
            _ratio(float(_counts(row, kind).get("supported_predicted_count") or 0), float(_counts(row, kind).get("predicted_count") or 0))
            for row in rows
        ]
        output.append(
            {
                "profile": profile,
                "kind": kind,
                "model_rows": len(rows),
                "specs": len({str(row.get("spec_id")).zfill(3) for row in rows if row.get("spec_id") is not None}),
                "gold_count": gold,
                "predicted_count": predicted,
                "represented_gold_count": represented,
                "supported_predicted_count": supported,
                "micro_precision": round(_ratio(supported, predicted), 6),
                "micro_recall": round(_ratio(represented, gold), 6),
                "mean_precision": round(statistics.mean(row_precisions), 6) if row_precisions else "",
                "mean_recall": round(statistics.mean(row_recalls), 6) if row_recalls else "",
                "median_precision": round(statistics.median(row_precisions), 6) if row_precisions else "",
                "median_recall": round(statistics.median(row_recalls), 6) if row_recalls else "",
                "mean_judge_precision_sd": round(statistics.mean(rel_precision), 6) if rel_precision else "",
                "mean_judge_recall_sd": round(statistics.mean(rel_recall), 6) if rel_recall else "",
            }
        )
    return output


def _safe_profile_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    return text or "profile"


def _profile_rows(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    majority_path = run_dir / "repeated_judge" / "majority_scores.json"
    if not majority_path.exists():
        raise FileNotFoundError(f"Missing judged score file: {majority_path}")
    rows = load_json(majority_path)
    if not isinstance(rows, list):
        raise ValueError("repeated_judge/majority_scores.json must contain a JSON list.")
    profile_manifest_path = run_dir / "profile_manifest.json"
    profile_manifest = load_json(profile_manifest_path) if profile_manifest_path.exists() else {}
    profile = profile_manifest.get("profile")
    checkpoint_labels = sorted({str(row.get("checkpoint_label") or "") for row in rows if row.get("checkpoint_label")})
    if len(checkpoint_labels) > 1:
        return {
            _safe_profile_name(label): [row for row in rows if str(row.get("checkpoint_label") or "") == label]
            for label in checkpoint_labels
        }
    if isinstance(profile, str) and profile:
        return {_safe_profile_name(profile): rows}
    if checkpoint_labels:
        return {_safe_profile_name(checkpoint_labels[0]): rows}
    return {_safe_profile_name(run_dir.name): rows}


def _reliability_rows(run_dir: Path, checkpoint_labels: set[str]) -> list[dict[str, Any]]:
    path = run_dir / "repeated_judge" / "judge_reliability_by_model.json"
    if not path.exists():
        return []
    rows = load_json(path)
    if not isinstance(rows, list):
        return []
    if not checkpoint_labels:
        return [row for row in rows if isinstance(row, dict)]
    return [row for row in rows if isinstance(row, dict) and str(row.get("checkpoint_label") or "") in checkpoint_labels]


def _canonical_rows(run_dir: Path, profiles: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    try:
        checkpoints = read_checkpoint_manifest(run_dir)
    except FileNotFoundError:
        checkpoints = []
    checkpoint_index = {
        (
            str(row.get("spec_id")).zfill(3),
            str(row.get("generation_run_id") or row.get("generation_id") or ""),
            str(row.get("checkpoint_label") or ""),
        ): row
        for row in checkpoints
    }
    canonical: list[dict[str, Any]] = []
    for profile, rows in profiles.items():
        for row in rows:
            spec_id = str(row.get("spec_id")).zfill(3)
            generation_id = str(row.get("generation_run_id") or row.get("generation_id") or "")
            checkpoint_label = str(row.get("checkpoint_label") or "")
            checkpoint = checkpoint_index.get((spec_id, generation_id, checkpoint_label), {})
            canonical.append(
                {
                    "profile": profile,
                    "spec_id": spec_id,
                    "generation_id": generation_id,
                    "checkpoint_label": checkpoint_label,
                    "spec_path": checkpoint.get("spec_path", ""),
                    "reference_model_path": checkpoint.get("reference_model_path", ""),
                    "generated_model_path": checkpoint.get("model_path", checkpoint.get("generated_model_path", "")),
                    "plantuml_path": checkpoint.get("plantuml_path", ""),
                    "judge_output_paths": row.get("judge_output_paths", []),
                    "provider": checkpoint.get("provider", row.get("provider", "")),
                    "model": checkpoint.get("model", row.get("model", "")),
                    "status": "scored" if row.get("complete", True) else "incomplete",
                }
            )
    return canonical


def aggregate_judged_run(run_dir: Path, out_dir: Path) -> list[dict[str, Any]]:
    profiles = _profile_rows(run_dir)
    summary_rows: list[dict[str, Any]] = []
    for profile, rows in profiles.items():
        checkpoint_labels = {str(row.get("checkpoint_label") or "") for row in rows if row.get("checkpoint_label")}
        summary_rows.extend(summarize_profile(profile, rows, _reliability_rows(run_dir, checkpoint_labels)))

    fields = [
        "profile",
        "kind",
        "model_rows",
        "specs",
        "gold_count",
        "predicted_count",
        "represented_gold_count",
        "supported_predicted_count",
        "micro_precision",
        "micro_recall",
        "mean_precision",
        "mean_recall",
        "median_precision",
        "median_recall",
        "mean_judge_precision_sd",
        "mean_judge_recall_sd",
    ]
    write_json(out_dir / "profile_summary.json", summary_rows)
    write_csv(out_dir / "profile_summary.csv", summary_rows, fields)
    write_canonical_run_manifest(out_dir, _canonical_rows(run_dir, profiles))
    return summary_rows
