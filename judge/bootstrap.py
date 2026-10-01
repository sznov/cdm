from __future__ import annotations

import random
from collections.abc import Callable
from statistics import mean
from typing import Any

from judge.repeated import percentile, prf


KINDS = {
    "overall": None,
    "entity": "entities",
    "attribute": "attributes",
    "relationship": "relationships",
    "identifier": "identifiers",
}


def _counts(row: dict[str, Any], kind: str) -> dict[str, int]:
    source = row if KINDS[kind] is None else (row.get("by_kind") or {}).get(KINDS[kind]) or {}
    return {
        "gold_count": int(source.get("gold_count") or 0),
        "predicted_count": int(source.get("predicted_count") or 0),
        "represented_gold_count": int(source.get("represented_gold_count") or 0),
        "supported_predicted_count": int(source.get("supported_predicted_count") or 0),
    }


def _metric_value(rows: list[dict[str, Any]], kind: str, metric: str) -> float:
    if not rows:
        return 0.0
    if metric.startswith("micro_"):
        total = {
            "gold_count": 0,
            "predicted_count": 0,
            "represented_gold_count": 0,
            "supported_predicted_count": 0,
        }
        for row in rows:
            counts = _counts(row, kind)
            for key in total:
                total[key] += counts[key]
        score = prf(**total)
        return float(score[metric.removeprefix("micro_")])
    if metric.startswith("mean_"):
        base_metric = metric.removeprefix("mean_")
        values = [float(prf(**_counts(row, kind))[base_metric]) for row in rows]
        return mean(values) if values else 0.0
    raise ValueError(f"Unsupported bootstrap metric: {metric}")


def _hierarchical_samples(
    rows: list[dict[str, Any]],
    *,
    samples: int,
    seed: int,
    scorer: Callable[[list[dict[str, Any]]], float],
) -> list[float]:
    if samples <= 0 or not rows:
        return []
    rng = random.Random(seed)
    by_spec: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_spec.setdefault(str(row.get("spec_id") or "").zfill(3), []).append(row)
    spec_ids = sorted(by_spec)
    values: list[float] = []
    for _ in range(samples):
        sampled_rows: list[dict[str, Any]] = []
        for _slot in spec_ids:
            spec_id = rng.choice(spec_ids)
            spec_rows = by_spec[spec_id]
            sampled_rows.extend(rng.choice(spec_rows) for _ in spec_rows)
        values.append(scorer(sampled_rows))
    return values


def hierarchical_bootstrap_ci(
    rows: list[dict[str, Any]],
    *,
    profile: str,
    samples: int = 5000,
    seed: int = 20260523,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    metrics = ("micro_precision", "micro_recall", "mean_precision", "mean_recall")
    for kind in KINDS:
        for metric in metrics:
            observed = _metric_value(rows, kind, metric)
            values = _hierarchical_samples(
                rows,
                samples=samples,
                seed=seed,
                scorer=lambda sampled, kind=kind, metric=metric: _metric_value(sampled, kind, metric),
            )
            output.append(
                {
                    "profile": profile,
                    "kind": kind,
                    "metric": metric,
                    "model_rows": len(rows),
                    "specs": len({str(row.get("spec_id") or "").zfill(3) for row in rows}),
                    "samples": samples,
                    "mean": round(observed, 6),
                    "ci95_low": round(float(percentile(values, 0.025) or observed), 6),
                    "ci95_high": round(float(percentile(values, 0.975) or observed), 6),
                }
            )
    return output


def paired_delta_bootstrap_ci(
    rows_a: list[dict[str, Any]],
    rows_b: list[dict[str, Any]],
    *,
    comparison: str,
    samples: int = 5000,
    seed: int = 20260523,
) -> list[dict[str, Any]]:
    by_key_a = {
        (str(row.get("spec_id") or "").zfill(3), str(row.get("generation_run_id") or row.get("generation_id") or "")): row
        for row in rows_a
    }
    by_key_b = {
        (str(row.get("spec_id") or "").zfill(3), str(row.get("generation_run_id") or row.get("generation_id") or "")): row
        for row in rows_b
    }
    pairs = [(row_a, by_key_b[key]) for key, row_a in by_key_a.items() if key in by_key_b]
    delta_rows = [
        {
            "spec_id": left.get("spec_id"),
            "generation_run_id": left.get("generation_run_id") or left.get("generation_id"),
            "left": left,
            "right": right,
        }
        for left, right in pairs
    ]

    def delta_metric(sampled_pairs: list[dict[str, Any]], kind: str, metric: str) -> float:
        left_rows = [row["left"] for row in sampled_pairs]
        right_rows = [row["right"] for row in sampled_pairs]
        return _metric_value(right_rows, kind, metric) - _metric_value(left_rows, kind, metric)

    output: list[dict[str, Any]] = []
    metrics = ("micro_precision", "micro_recall", "mean_precision", "mean_recall")
    for kind in KINDS:
        for metric in metrics:
            observed = delta_metric(delta_rows, kind, metric) if delta_rows else 0.0
            values = _hierarchical_samples(
                delta_rows,
                samples=samples,
                seed=seed,
                scorer=lambda sampled, kind=kind, metric=metric: delta_metric(sampled, kind, metric),
            )
            output.append(
                {
                    "comparison": comparison,
                    "kind": kind,
                    "metric": f"{metric}_delta",
                    "paired_rows": len(delta_rows),
                    "specs": len({str(row.get("spec_id") or "").zfill(3) for row in delta_rows}),
                    "samples": samples,
                    "mean": round(observed, 6),
                    "ci95_low": round(float(percentile(values, 0.025) or observed), 6),
                    "ci95_high": round(float(percentile(values, 0.975) or observed), 6),
                }
            )
    return output


__all__ = ["hierarchical_bootstrap_ci", "paired_delta_bootstrap_ci"]
