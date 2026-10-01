from __future__ import annotations

import math
import random
import statistics
from pathlib import Path
from typing import Any

from core.artifacts import load_json, write_csv, write_json


KINDS = ("entities", "relationships", "attributes", "identifiers")
METRICS = ("precision", "recall", "f1", "macro_f1")


def round4(value: float) -> float:
    return round(float(value), 4)


def prf(*, gold_count: int, predicted_count: int, represented_gold_count: int, supported_predicted_count: int) -> dict[str, Any]:
    precision = supported_predicted_count / predicted_count if predicted_count else 0.0
    recall = represented_gold_count / gold_count if gold_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "gold_count": gold_count,
        "predicted_count": predicted_count,
        "represented_gold_count": represented_gold_count,
        "supported_predicted_count": supported_predicted_count,
        "precision": round4(precision),
        "recall": round4(recall),
        "f1": round4(f1),
    }


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * pct
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def stdev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def model_key(row: dict[str, Any], ordinal: int) -> str:
    return (
        f"{str(row.get('spec_id') or '').zfill(3)}::"
        f"{row.get('generation_run_id') or 'gen-001'}::"
        f"{row.get('checkpoint_label') or 'checkpoint'}::{ordinal:04d}"
    )


def ids_from_entries(entries: list[dict[str, Any]], field: str) -> set[str]:
    ids: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict) and entry.get(field):
            ids.add(str(entry[field]))
    return ids


def score_from_counts(by_kind_counts: dict[str, dict[str, int]]) -> dict[str, Any]:
    by_kind: dict[str, Any] = {}
    macro_values: list[float] = []
    total = {
        "gold_count": 0,
        "predicted_count": 0,
        "represented_gold_count": 0,
        "supported_predicted_count": 0,
    }
    for kind in KINDS:
        counts = by_kind_counts[kind]
        kind_score = prf(**counts)
        kind_score["kind"] = kind
        by_kind[kind] = kind_score
        macro_values.append(float(kind_score["f1"]))
        for key in total:
            total[key] += int(counts[key])
    aggregate = prf(**total)
    aggregate["macro_f1"] = round4(sum(macro_values) / len(macro_values)) if macro_values else 0.0
    return {"aggregate": aggregate, "by_kind": by_kind}


def vote_histogram(values: Any, expected_repeats: int) -> dict[str, int]:
    histogram = {str(index): 0 for index in range(expected_repeats + 1)}
    for value in values:
        key = str(int(value))
        histogram[key] = histogram.get(key, 0) + 1
    return histogram


def load_directional_score(result: dict[str, Any]) -> dict[str, Any] | None:
    inline_score = result.get("directional_semantic_score")
    if isinstance(inline_score, dict):
        return inline_score
    eval_path = result.get("evaluation_path")
    if not eval_path:
        return None
    path = Path(str(eval_path))
    if not path.exists():
        return None
    data = load_json(path)
    score = data.get("directional_semantic_score") if isinstance(data, dict) else None
    return score if isinstance(score, dict) else None


def degenerate_zero_directional_reason(evaluation_path: Path) -> str:
    try:
        data = load_json(evaluation_path)
    except Exception as exc:
        return f"could not parse evaluation output: {exc}"
    if not isinstance(data, dict):
        return "evaluation output is not an object"
    score = data.get("directional_semantic_score")
    if not isinstance(score, dict):
        return ""
    aggregate = score.get("aggregate")
    if not isinstance(aggregate, dict):
        return ""
    try:
        gold_count = int(aggregate.get("gold_count") or 0)
        predicted_count = int(aggregate.get("predicted_count") or 0)
        represented = int(aggregate.get("represented_gold_count") or 0)
        supported = int(aggregate.get("supported_predicted_count") or 0)
    except (TypeError, ValueError):
        return ""
    if gold_count > 0 and predicted_count > 0 and represented == 0 and supported == 0:
        return (
            "directional semantic judge returned zero represented/supported artifacts "
            f"despite {gold_count} gold and {predicted_count} predicted artifacts"
        )
    return ""


def majority_for_model(
    row: dict[str, Any],
    results: list[dict[str, Any]],
    expected_repeats: int,
    majority_threshold: int | None = None,
) -> dict[str, Any]:
    scores = [load_directional_score(result) for result in results if result.get("status") == "completed"]
    scores = [score for score in scores if isinstance(score, dict)]
    completed = len(scores)
    threshold = (
        int(majority_threshold)
        if majority_threshold is not None
        else expected_repeats // 2 + 1
    )
    if threshold < 1 or threshold > expected_repeats:
        raise ValueError("majority_threshold must be between one and expected_repeats")
    by_kind_counts: dict[str, dict[str, int]] = {}
    agreement: dict[str, Any] = {}

    for kind in KINDS:
        first_kind = (scores[0].get("by_kind", {}).get(kind, {}) if scores else {})
        gold_count = int(first_kind.get("gold_count", 0) or 0)
        predicted_count = int(first_kind.get("predicted_count", 0) or 0)
        represented_votes: dict[str, int] = {}
        supported_votes: dict[str, int] = {}
        for score in scores:
            kind_score = score.get("by_kind", {}).get(kind, {})
            for artifact_id in ids_from_entries(kind_score.get("represented") or [], "id"):
                represented_votes[artifact_id] = represented_votes.get(artifact_id, 0) + 1
            for artifact_id in ids_from_entries(kind_score.get("supported") or [], "id"):
                supported_votes[artifact_id] = supported_votes.get(artifact_id, 0) + 1
        represented_gold_count = sum(1 for count in represented_votes.values() if count >= threshold)
        supported_predicted_count = sum(1 for count in supported_votes.values() if count >= threshold)
        by_kind_counts[kind] = {
            "gold_count": gold_count,
            "predicted_count": predicted_count,
            "represented_gold_count": represented_gold_count,
            "supported_predicted_count": supported_predicted_count,
        }
        agreement[kind] = {
            "coverage_vote_counts": vote_histogram(represented_votes.values(), expected_repeats),
            "support_vote_counts": vote_histogram(supported_votes.values(), expected_repeats),
            "coverage_unvoted_count": max(gold_count - len(represented_votes), 0),
            "support_unvoted_count": max(predicted_count - len(supported_votes), 0),
        }

    score = score_from_counts(by_kind_counts)
    return {
        "model_key": row["model_key"],
        "spec_id": row["spec_id"],
        "generation_run_id": row["generation_run_id"],
        "checkpoint_label": row["checkpoint_label"],
        "source_snapshot_id": row.get("source_snapshot_id"),
        "source_snapshot_index": row.get("source_snapshot_index"),
        "judge_repeats_expected": expected_repeats,
        "judge_repeats_completed": completed,
        "majority_threshold": threshold,
        "complete": completed == expected_repeats,
        **score["aggregate"],
        "by_kind": score["by_kind"],
        "agreement": agreement,
        "judge_output_paths": [
            str(result.get("evaluation_path"))
            for result in results
            if result.get("status") == "completed" and result.get("evaluation_path")
        ],
    }


def per_judge_rows(model_rows: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {row["model_key"]: row for row in model_rows}
    rows: list[dict[str, Any]] = []
    for result in results:
        score = load_directional_score(result)
        if not score:
            continue
        model = by_key.get(str(result.get("model_key") or ""))
        if not model:
            continue
        aggregate = score.get("aggregate", {})
        rows.append(
            {
                "model_key": model["model_key"],
                "spec_id": model["spec_id"],
                "generation_run_id": model["generation_run_id"],
                "checkpoint_label": model["checkpoint_label"],
                "repeat_index": result.get("repeat_index"),
                "precision": aggregate.get("precision"),
                "recall": aggregate.get("recall"),
                "f1": aggregate.get("f1"),
                "macro_f1": aggregate.get("macro_f1"),
            }
        )
    return rows


def reliability_rows(judge_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in judge_rows:
        grouped.setdefault(str(row["model_key"]), []).append(row)
    rows: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        first = items[0]
        output = {
            "model_key": key,
            "spec_id": first["spec_id"],
            "generation_run_id": first["generation_run_id"],
            "checkpoint_label": first["checkpoint_label"],
            "judge_repeats_completed": len(items),
        }
        for metric in METRICS:
            values = [float(item[metric]) for item in items if item.get(metric) is not None]
            output[f"{metric}_mean"] = round4(statistics.mean(values)) if values else ""
            output[f"{metric}_median"] = round4(statistics.median(values)) if values else ""
            output[f"{metric}_sd"] = round4(stdev(values)) if values else ""
        rows.append(output)
    return rows


def aggregate_majority_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_checkpoint: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_checkpoint.setdefault(str(row["checkpoint_label"]), []).append(row)
    summaries: list[dict[str, Any]] = []
    for checkpoint, checkpoint_rows in sorted(by_checkpoint.items()):
        spec_ids = sorted({str(row["spec_id"]) for row in checkpoint_rows})
        spec_means: dict[str, dict[str, float]] = {}
        for spec_id in spec_ids:
            spec_rows = [row for row in checkpoint_rows if str(row["spec_id"]) == spec_id]
            spec_means[spec_id] = {metric: statistics.mean(float(row[metric]) for row in spec_rows) for metric in METRICS}
        f1_values = [float(row["f1"]) for row in checkpoint_rows]
        summary: dict[str, Any] = {
            "checkpoint_label": checkpoint,
            "spec_count": len(spec_ids),
            "model_count": len(checkpoint_rows),
        }
        for metric in METRICS:
            spec_values = [values[metric] for values in spec_means.values()]
            model_values = [float(row[metric]) for row in checkpoint_rows]
            summary[f"primary_mean_{metric}"] = round4(statistics.mean(spec_values)) if spec_values else ""
            summary[f"model_mean_{metric}"] = round4(statistics.mean(model_values)) if model_values else ""
            summary[f"model_median_{metric}"] = round4(statistics.median(model_values)) if model_values else ""
            summary[f"model_sd_{metric}"] = round4(stdev(model_values)) if model_values else ""
        for label, pct in (("min", 0.0), ("p10", 0.10), ("p25", 0.25), ("p75", 0.75), ("p90", 0.90), ("max", 1.0)):
            value = percentile(f1_values, pct)
            summary[f"model_{label}_f1"] = round4(value) if value is not None else ""
        summaries.append(summary)
    return summaries


def aggregate_reliability_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_checkpoint: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_checkpoint.setdefault(str(row["checkpoint_label"]), []).append(row)
    summaries: list[dict[str, Any]] = []
    for checkpoint, checkpoint_rows in sorted(by_checkpoint.items()):
        summary: dict[str, Any] = {"checkpoint_label": checkpoint, "model_count": len(checkpoint_rows)}
        for metric in METRICS:
            values = [float(row[f"{metric}_sd"]) for row in checkpoint_rows if row.get(f"{metric}_sd") not in {None, ""}]
            summary[f"mean_judge_{metric}_sd"] = round4(statistics.mean(values)) if values else ""
            summary[f"median_judge_{metric}_sd"] = round4(statistics.median(values)) if values else ""
        summaries.append(summary)
    return summaries


def bootstrap_ci(judge_rows: list[dict[str, Any]], samples: int, seed: int) -> list[dict[str, Any]]:
    if samples <= 0:
        return []
    rng = random.Random(seed)
    by_checkpoint: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
    for row in judge_rows:
        by_checkpoint.setdefault(str(row["checkpoint_label"]), {}).setdefault(str(row["spec_id"]), {}).setdefault(
            str(row["generation_run_id"]), []
        ).append(row)

    output: list[dict[str, Any]] = []
    for checkpoint, by_spec in sorted(by_checkpoint.items()):
        spec_ids = sorted(by_spec)
        if not spec_ids:
            continue
        for metric in METRICS:
            sampled_values: list[float] = []
            for _ in range(samples):
                sampled_specs = [rng.choice(spec_ids) for _ in spec_ids]
                spec_means: list[float] = []
                for spec_id in sampled_specs:
                    gen_ids = sorted(by_spec[spec_id])
                    sampled_gens = [rng.choice(gen_ids) for _ in gen_ids]
                    gen_means: list[float] = []
                    for gen_id in sampled_gens:
                        rows = by_spec[spec_id][gen_id]
                        sampled_judges = [rng.choice(rows) for _ in rows]
                        gen_means.append(statistics.mean(float(row[metric]) for row in sampled_judges))
                    spec_means.append(statistics.mean(gen_means))
                sampled_values.append(statistics.mean(spec_means))
            output.append(
                {
                    "checkpoint_label": checkpoint,
                    "metric": metric,
                    "samples": samples,
                    "mean": round4(statistics.mean(sampled_values)),
                    "ci95_low": round4(percentile(sampled_values, 0.025) or 0.0),
                    "ci95_high": round4(percentile(sampled_values, 0.975) or 0.0),
                }
            )
    return output


def token_value(usage: dict[str, Any] | None, *keys: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    for key in keys:
        value = usage.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def judge_call_accounting(results: list[dict[str, Any]], *, judge_model: str, judge_provider: str = "llm") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        usage = None
        if result.get("evaluation_path") and Path(str(result["evaluation_path"])).exists():
            data = load_json(Path(str(result["evaluation_path"])))
            judge = data.get("directional_semantic_judge") if isinstance(data, dict) else None
            if isinstance(judge, dict):
                usage = judge.get("usage") if isinstance(judge.get("usage"), dict) else None
        prompt_details = usage.get("prompt_tokens_details") if isinstance(usage, dict) and isinstance(usage.get("prompt_tokens_details"), dict) else {}
        completion_details = (
            usage.get("completion_tokens_details")
            if isinstance(usage, dict) and isinstance(usage.get("completion_tokens_details"), dict)
            else {}
        )
        rows.append(
            {
                "call_id": f"{result.get('model_key')}::judge-{int(result.get('repeat_index') or 0):03d}",
                "phase": "semantic_judge",
                "spec_id": result.get("spec_id"),
                "generation_run_id": result.get("generation_run_id"),
                "checkpoint_label": result.get("checkpoint_label"),
                "provider": judge_provider,
                "model": judge_model,
                "harness_id": "directional-semantic-judge",
                "template_id": "build_directional_model_judge_messages",
                "started_at_utc": None,
                "ended_at_utc": None,
                "duration_seconds": result.get("seconds"),
                "status": result.get("status"),
                "retry_index": result.get("retry_index", 0),
                "http_status_or_error": result.get("error") or result.get("stderr"),
                "input_tokens": token_value(usage, "prompt_tokens", "input_tokens"),
                "output_tokens": token_value(usage, "completion_tokens", "output_tokens"),
                "total_tokens": token_value(usage, "total_tokens"),
                "cached_input_tokens": token_value(prompt_details, "cached_tokens", "cached_input_tokens"),
                "reasoning_tokens": token_value(completion_details, "reasoning_tokens"),
                "estimated_cost_usd": None,
                "pricing_manifest_id": None,
                "evaluation_path": result.get("evaluation_path"),
            }
        )
    return rows


def normalize_model_rows(raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    model_rows: list[dict[str, Any]] = []
    for ordinal, row in enumerate(raw_rows, start=1):
        model_path = row.get("model_path") or row.get("generated_model_path")
        gold_path = row.get("gold_path") or row.get("reference_model_path")
        spec_path = row.get("spec_path")
        if not all((row.get("spec_id"), model_path, gold_path, spec_path)):
            continue
        normalized = dict(row)
        normalized["spec_id"] = str(row.get("spec_id") or "").zfill(3)
        normalized["generation_run_id"] = str(row.get("generation_run_id") or row.get("generation_id") or "gen-001")
        normalized["checkpoint_label"] = str(row.get("checkpoint_label") or "checkpoint")
        normalized["model_path"] = str(model_path)
        normalized["gold_path"] = str(gold_path)
        normalized["spec_path"] = str(spec_path)
        normalized["model_key"] = model_key(normalized, ordinal)
        model_rows.append(normalized)
    return model_rows


def build_repeated_judge_reports(
    model_rows: list[dict[str, Any]],
    results: list[dict[str, Any]],
    *,
    judge_repeats: int,
    judge_model: str,
    judge_provider: str = "llm",
    bootstrap_samples: int = 0,
    bootstrap_seed: int = 20260523,
) -> dict[str, list[dict[str, Any]]]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        by_model.setdefault(str(result.get("model_key") or ""), []).append(result)
    majority_rows = [majority_for_model(row, by_model.get(row["model_key"], []), judge_repeats) for row in model_rows]
    judge_rows = per_judge_rows(model_rows, results)
    reliability = reliability_rows(judge_rows)
    return {
        "majority_scores": majority_rows,
        "per_judge_scores": judge_rows,
        "judge_reliability_by_model": reliability,
        "judge_call_accounting": judge_call_accounting(results, judge_model=judge_model, judge_provider=judge_provider),
        "checkpoint_summary": aggregate_majority_rows(majority_rows),
        "judge_reliability_summary": aggregate_reliability_rows(reliability),
        "bootstrap_ci": bootstrap_ci(judge_rows, bootstrap_samples, bootstrap_seed),
    }


def write_repeated_judge_reports(output_dir: Path, reports: dict[str, list[dict[str, Any]]]) -> None:
    for name, rows in reports.items():
        write_json(output_dir / f"{name}.json", rows)

    majority_csv_rows = [
        {
            key: row.get(key)
            for key in (
                "model_key",
                "spec_id",
                "generation_run_id",
                "checkpoint_label",
                "source_snapshot_id",
                "source_snapshot_index",
                "judge_repeats_expected",
                "judge_repeats_completed",
                "majority_threshold",
                "complete",
                "gold_count",
                "predicted_count",
                "represented_gold_count",
                "supported_predicted_count",
                "precision",
                "recall",
                "f1",
                "macro_f1",
            )
        }
        for row in reports["majority_scores"]
    ]
    write_csv(
        output_dir / "majority_scores.csv",
        majority_csv_rows,
        [
            "model_key",
            "spec_id",
            "generation_run_id",
            "checkpoint_label",
            "source_snapshot_id",
            "source_snapshot_index",
            "judge_repeats_expected",
            "judge_repeats_completed",
            "majority_threshold",
            "complete",
            "gold_count",
            "predicted_count",
            "represented_gold_count",
            "supported_predicted_count",
            "precision",
            "recall",
            "f1",
            "macro_f1",
        ],
    )
    write_csv(
        output_dir / "per_judge_scores.csv",
        reports["per_judge_scores"],
        ["model_key", "spec_id", "generation_run_id", "checkpoint_label", "repeat_index", *METRICS],
    )
    write_csv(
        output_dir / "judge_reliability_by_model.csv",
        reports["judge_reliability_by_model"],
        [
            "model_key",
            "spec_id",
            "generation_run_id",
            "checkpoint_label",
            "judge_repeats_completed",
            *[f"{metric}_{suffix}" for metric in METRICS for suffix in ("mean", "median", "sd")],
        ],
    )
    write_csv(
        output_dir / "judge_call_accounting.csv",
        reports["judge_call_accounting"],
        [
            "call_id",
            "phase",
            "spec_id",
            "generation_run_id",
            "checkpoint_label",
            "provider",
            "model",
            "harness_id",
            "template_id",
            "started_at_utc",
            "ended_at_utc",
            "duration_seconds",
            "status",
            "retry_index",
            "http_status_or_error",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "estimated_cost_usd",
            "pricing_manifest_id",
            "evaluation_path",
        ],
    )
    write_csv(
        output_dir / "checkpoint_summary.csv",
        reports["checkpoint_summary"],
        [
            "checkpoint_label",
            "spec_count",
            "model_count",
            *[f"primary_mean_{metric}" for metric in METRICS],
            *[f"model_mean_{metric}" for metric in METRICS],
            *[f"model_median_{metric}" for metric in METRICS],
            *[f"model_sd_{metric}" for metric in METRICS],
            "model_min_f1",
            "model_p10_f1",
            "model_p25_f1",
            "model_p75_f1",
            "model_p90_f1",
            "model_max_f1",
        ],
    )
    write_csv(
        output_dir / "judge_reliability_summary.csv",
        reports["judge_reliability_summary"],
        [
            "checkpoint_label",
            "model_count",
            *[f"{agg}_judge_{metric}_sd" for metric in METRICS for agg in ("mean", "median")],
        ],
    )
    write_csv(output_dir / "bootstrap_ci.csv", reports["bootstrap_ci"], ["checkpoint_label", "metric", "samples", "mean", "ci95_low", "ci95_high"])


__all__ = [
    "KINDS",
    "METRICS",
    "build_repeated_judge_reports",
    "degenerate_zero_directional_reason",
    "majority_for_model",
    "model_key",
    "normalize_model_rows",
    "per_judge_rows",
    "reliability_rows",
    "write_repeated_judge_reports",
]
