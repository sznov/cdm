from __future__ import annotations

import csv
import hashlib
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from judge.evaluation_artifacts import write_json_atomic
from judge.evaluation_contracts import (
    EvaluationClaim,
    EvaluationClaimsManifest,
    EvaluationSuite,
    JudgeResultRecord,
    MetricDefinition,
)
from judge.repeated import majority_for_model, percentile


class EvaluationReportError(ValueError):
    pass


def _round(value: float) -> float:
    return round(float(value), 8)


def _candidate_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row["system_id"]),
        str(row["case_id"]),
        str(row["sample_id"]),
        str(row["checkpoint_or_view"]),
    )


def _result_key(row: JudgeResultRecord) -> tuple[str, str, str, str, str]:
    return (
        row.judge_id,
        row.system_id,
        row.case_id,
        row.sample_id,
        row.checkpoint_or_view,
    )


def validate_result_metrics(
    result: JudgeResultRecord,
    metrics: dict[str, MetricDefinition],
) -> None:
    unknown = sorted(set(result.metrics) - set(metrics))
    if unknown:
        raise EvaluationReportError(
            f"judge result {result.result_id!r} contains undeclared metrics: "
            + ", ".join(unknown)
        )
    for metric_id, value in result.metrics.items():
        definition = metrics[metric_id]
        if definition.minimum is not None and value < definition.minimum:
            raise EvaluationReportError(
                f"metric {metric_id!r} is below its declared minimum"
            )
        if definition.maximum is not None and value > definition.maximum:
            raise EvaluationReportError(
                f"metric {metric_id!r} exceeds its declared maximum"
            )


def _reduce_numeric(
    values: list[float],
    definition: MetricDefinition,
) -> float:
    if definition.repeat_reduction == "mean":
        return statistics.mean(values)
    if definition.repeat_reduction == "median":
        return statistics.median(values)
    raise EvaluationReportError(
        f"metric {definition.metric_id!r} requires directional majority data"
    )


def _directional_reduction(
    *,
    candidate: dict[str, Any],
    rows: list[JudgeResultRecord],
    expected_repeats: int,
    majority_threshold: int,
) -> dict[str, Any]:
    model_key = "::".join(_candidate_key(candidate))
    model_row = {
        "model_key": model_key,
        "spec_id": candidate["case_id"],
        "generation_run_id": candidate["sample_id"],
        "checkpoint_label": candidate["checkpoint_or_view"],
    }
    legacy_results = [
        {
            "status": "completed",
            "model_key": model_key,
            "directional_semantic_score": result.details.get(
                "directional_semantic_score"
            ),
        }
        for result in rows
        if result.status == "completed"
        and isinstance(result.details.get("directional_semantic_score"), dict)
    ]
    majority = majority_for_model(
        model_row,
        legacy_results,
        expected_repeats,
        majority_threshold,
    )
    aggregate = {
        key: majority[key]
        for key in (
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
    return {
        "metrics": {
            "precision": float(majority["precision"]),
            "recall": float(majority["recall"]),
            "f1": float(majority["f1"]),
            "macro_f1": float(majority["macro_f1"]),
        },
        "directional_counts": aggregate,
        "by_kind": majority["by_kind"],
        "agreement": majority["agreement"],
        "complete": bool(majority["complete"]),
        "completed_repeats": int(majority["judge_repeats_completed"]),
    }


def reduce_judge_results(
    *,
    suite: EvaluationSuite,
    candidates: list[dict[str, Any]],
    results: list[JudgeResultRecord],
) -> list[dict[str, Any]]:
    metric_definitions = {metric.metric_id: metric for metric in suite.metrics}
    for result in results:
        validate_result_metrics(result, metric_definitions)
    by_key: dict[tuple[str, str, str, str, str], list[JudgeResultRecord]] = (
        defaultdict(list)
    )
    for result in results:
        by_key[_result_key(result)].append(result)
    judge_by_id = {judge.judge_id: judge for judge in suite.judges}
    reduced: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=_candidate_key):
        for judge_id, judge in sorted(judge_by_id.items()):
            key = (judge_id, *_candidate_key(candidate))
            rows = sorted(by_key.get(key, []), key=lambda row: row.repeat_index)
            completed = [row for row in rows if row.status == "completed"]
            base: dict[str, Any] = {
                "judge_id": judge_id,
                "system_id": candidate["system_id"],
                "case_id": candidate["case_id"],
                "sample_id": candidate["sample_id"],
                "checkpoint_or_view": candidate["checkpoint_or_view"],
                "expected_repeats": int(judge.repetitions),
                "completed_repeats": len(completed),
                "complete": len(completed) == int(judge.repetitions),
                "metrics": {},
            }
            if (
                judge.kind == "directional_structured_model_v1"
                or (
                    judge.kind == "stored_result_manifest"
                    and judge.reducer_revision == "directional-majority-v1"
                )
            ):
                threshold = judge.majority_threshold or (judge.repetitions // 2 + 1)
                base.update(
                    _directional_reduction(
                        candidate=candidate,
                        rows=rows,
                        expected_repeats=judge.repetitions,
                        majority_threshold=threshold,
                    )
                )
            else:
                complete_metric_ids: set[str] = set()
                for metric_id, definition in metric_definitions.items():
                    values = [
                        float(row.metrics[metric_id])
                        for row in completed
                        if metric_id in row.metrics
                    ]
                    if values and definition.repeat_reduction != "directional_majority_v1":
                        base["metrics"][metric_id] = _round(
                            _reduce_numeric(values, definition)
                        )
                        if len(values) == int(judge.repetitions):
                            complete_metric_ids.add(metric_id)
                expected_metric_ids = {
                    metric_id
                    for metric_id, definition in metric_definitions.items()
                    if definition.repeat_reduction in {"mean", "median"}
                }
                base["complete"] = (
                    bool(expected_metric_ids)
                    and base["complete"]
                    and complete_metric_ids == expected_metric_ids
                )
            reduced.append(base)
    return reduced


def _micro_score(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    counts = {
        "gold_count": sum(
            int((row.get("directional_counts") or {}).get("gold_count") or 0)
            for row in rows
        ),
        "predicted_count": sum(
            int((row.get("directional_counts") or {}).get("predicted_count") or 0)
            for row in rows
        ),
        "represented_gold_count": sum(
            int(
                (row.get("directional_counts") or {}).get(
                    "represented_gold_count"
                )
                or 0
            )
            for row in rows
        ),
        "supported_predicted_count": sum(
            int(
                (row.get("directional_counts") or {}).get(
                    "supported_predicted_count"
                )
                or 0
            )
            for row in rows
        ),
    }
    precision = (
        counts["supported_predicted_count"] / counts["predicted_count"]
        if counts["predicted_count"]
        else 0.0
    )
    recall = (
        counts["represented_gold_count"] / counts["gold_count"]
        if counts["gold_count"]
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        **counts,
        "micro_precision": _round(precision),
        "micro_recall": _round(recall),
        "micro_f1": _round(f1),
    }


def _directional_kind_summaries(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, float | int]]:
    kinds = sorted(
        {
            kind
            for row in rows
            for kind in (row.get("by_kind") or {})
        }
    )
    output: dict[str, dict[str, float | int]] = {}
    for kind in kinds:
        kind_rows = [
            {"directional_counts": (row.get("by_kind") or {}).get(kind) or {}}
            for row in rows
        ]
        summary = _micro_score(kind_rows)
        recalls = [
            float(((row.get("by_kind") or {}).get(kind) or {}).get("recall") or 0.0)
            for row in rows
        ]
        precisions = [
            float(
                ((row.get("by_kind") or {}).get(kind) or {}).get("precision")
                or 0.0
            )
            for row in rows
        ]
        summary["median_precision"] = (
            _round(statistics.median(precisions)) if precisions else 0.0
        )
        summary["median_recall"] = (
            _round(statistics.median(recalls)) if recalls else 0.0
        )
        output[kind] = summary
    return output


def summarize_systems(
    reduced_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in reduced_rows:
        grouped[(str(row["system_id"]), str(row["judge_id"]))].append(row)
    summaries: list[dict[str, Any]] = []
    for (system_id, judge_id), rows in sorted(grouped.items()):
        complete_rows = [row for row in rows if row.get("complete")]
        metric_ids = sorted(
            {
                metric_id
                for row in complete_rows
                for metric_id in (row.get("metrics") or {})
            }
        )
        summary: dict[str, Any] = {
            "system_id": system_id,
            "judge_id": judge_id,
            "candidate_count": len(rows),
            "complete_candidate_count": len(complete_rows),
            "failed_candidate_count": len(rows) - len(complete_rows),
            "case_count": len({str(row["case_id"]) for row in rows}),
            "metrics": {},
        }
        for metric_id in metric_ids:
            values = [
                float(row["metrics"][metric_id])
                for row in complete_rows
                if metric_id in row.get("metrics", {})
            ]
            if not values:
                continue
            summary["metrics"][metric_id] = {
                "mean": _round(statistics.mean(values)),
                "median": _round(statistics.median(values)),
                "spread": _round(statistics.stdev(values))
                if len(values) > 1
                else 0.0,
                "count": len(values),
            }
        if any(row.get("directional_counts") for row in complete_rows):
            summary["directional_aggregate"] = _micro_score(complete_rows)
            summary["directional_by_kind"] = _directional_kind_summaries(
                complete_rows
            )
        summaries.append(summary)
    return summaries


def _stable_seed(base_seed: int, *parts: str) -> int:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).digest()
    return base_seed ^ int.from_bytes(digest[:8], "big")


def _confidence_bounds(confidence_level: float) -> tuple[float, float]:
    tail = (1.0 - confidence_level) / 2.0
    return tail, 1.0 - tail


def _percentile_value(
    values: list[float],
    percentile_value: float,
    *,
    fallback: float,
) -> float:
    value = percentile(values, percentile_value)
    return fallback if value is None else float(value)


_DIRECTIONAL_BOOTSTRAP_KINDS = {
    "overall": None,
    "entity": "entities",
    "attribute": "attributes",
    "relationship": "relationships",
    "identifier": "identifiers",
}


def _directional_metric_selector(
    metric_id: str,
) -> tuple[str, str] | None:
    if metric_id in {"micro_precision", "micro_recall", "micro_f1"}:
        return "overall", metric_id
    for artifact_kind in _DIRECTIONAL_BOOTSTRAP_KINDS:
        if artifact_kind == "overall":
            continue
        prefix = f"{artifact_kind}_"
        if metric_id.startswith(prefix):
            selected_metric = metric_id[len(prefix) :]
            if selected_metric in {
                "micro_precision",
                "micro_recall",
                "micro_f1",
            }:
                return artifact_kind, selected_metric
    return None


def _directional_counts(
    row: dict[str, Any],
    *,
    artifact_kind: str,
) -> dict[str, int]:
    source = (
        row.get("directional_counts") or {}
        if artifact_kind == "overall"
        else (
            (row.get("by_kind") or {}).get(
                _DIRECTIONAL_BOOTSTRAP_KINDS[artifact_kind]
            )
            or {}
        )
    )
    return {
        "gold_count": int(source.get("gold_count") or 0),
        "predicted_count": int(source.get("predicted_count") or 0),
        "represented_gold_count": int(
            source.get("represented_gold_count") or 0
        ),
        "supported_predicted_count": int(
            source.get("supported_predicted_count") or 0
        ),
    }


def _directional_micro_metrics(
    rows: list[dict[str, Any]],
    *,
    artifact_kind: str,
) -> dict[str, float]:
    total = {
        "gold_count": 0,
        "predicted_count": 0,
        "represented_gold_count": 0,
        "supported_predicted_count": 0,
    }
    for row in rows:
        counts = _directional_counts(row, artifact_kind=artifact_kind)
        for key in total:
            total[key] += counts[key]
    precision = (
        total["supported_predicted_count"] / total["predicted_count"]
        if total["predicted_count"]
        else 0.0
    )
    recall = (
        total["represented_gold_count"] / total["gold_count"]
        if total["gold_count"]
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": f1,
    }


def _directional_bootstrap_intervals(
    *,
    suite: EvaluationSuite,
    reduced_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    samples = suite.statistics.bootstrap_samples
    if samples <= 0:
        return []
    low_pct, high_pct = _confidence_bounds(
        suite.statistics.confidence_level
    )
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in reduced_rows:
        if row.get("complete") and row.get("directional_counts"):
            grouped[(str(row["system_id"]), str(row["judge_id"]))].append(row)
    output: list[dict[str, Any]] = []
    for (system_id, judge_id), rows in sorted(grouped.items()):
        by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_case[str(row["case_id"])].append(row)
        case_ids = sorted(by_case)
        rng = random.Random(suite.statistics.bootstrap_seed)
        distributions = {
            (artifact_kind, metric_id): []
            for artifact_kind in _DIRECTIONAL_BOOTSTRAP_KINDS
            for metric_id in (
                "micro_precision",
                "micro_recall",
                "micro_f1",
            )
        }
        for _ in range(samples):
            sampled_rows: list[dict[str, Any]] = []
            for _slot in case_ids:
                case_id = rng.choice(case_ids)
                case_rows = by_case[case_id]
                sampled_rows.extend(
                    rng.choice(case_rows) for _candidate_slot in case_rows
                )
            for artifact_kind in _DIRECTIONAL_BOOTSTRAP_KINDS:
                score = _directional_micro_metrics(
                    sampled_rows,
                    artifact_kind=artifact_kind,
                )
                for metric_id, value in score.items():
                    distributions[(artifact_kind, metric_id)].append(value)
        for artifact_kind in _DIRECTIONAL_BOOTSTRAP_KINDS:
            observed = _directional_micro_metrics(
                rows,
                artifact_kind=artifact_kind,
            )
            for metric_id, value in observed.items():
                sampled_values = distributions[(artifact_kind, metric_id)]
                output.append(
                    {
                        "system_id": system_id,
                        "judge_id": judge_id,
                        "artifact_kind": artifact_kind,
                        "metric_id": metric_id,
                        "aggregation": "micro",
                        "case_count": len(case_ids),
                        "samples": samples,
                        "seed": suite.statistics.bootstrap_seed,
                        "confidence_level": suite.statistics.confidence_level,
                        "observed": _round(value),
                        "ci_low": _round(
                            _percentile_value(
                                sampled_values,
                                low_pct,
                                fallback=value,
                            )
                        ),
                        "ci_high": _round(
                            _percentile_value(
                                sampled_values,
                                high_pct,
                                fallback=value,
                            )
                        ),
                    }
                )
    return output


def bootstrap_intervals(
    *,
    suite: EvaluationSuite,
    reduced_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    samples = suite.statistics.bootstrap_samples
    if samples <= 0:
        return []
    low_pct, high_pct = _confidence_bounds(suite.statistics.confidence_level)
    grouped: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in reduced_rows:
        if not row.get("complete"):
            continue
        for metric_id, value in (row.get("metrics") or {}).items():
            grouped[
                (str(row["system_id"]), str(row["judge_id"]), str(metric_id))
            ][str(row["case_id"])].append(float(value))
    output: list[dict[str, Any]] = []
    for (system_id, judge_id, metric_id), by_case in sorted(grouped.items()):
        case_ids = sorted(by_case)
        if not case_ids:
            continue
        rng = random.Random(
            _stable_seed(
                suite.statistics.bootstrap_seed,
                system_id,
                judge_id,
                metric_id,
            )
        )
        sampled_values: list[float] = []
        for _ in range(samples):
            sampled_cases = [rng.choice(case_ids) for _slot in case_ids]
            case_values: list[float] = []
            for case_id in sampled_cases:
                candidates = by_case[case_id]
                sampled_candidates = [
                    rng.choice(candidates) for _slot in candidates
                ]
                case_values.append(statistics.mean(sampled_candidates))
            sampled_values.append(statistics.mean(case_values))
        observed = statistics.mean(
            statistics.mean(values) for values in by_case.values()
        )
        output.append(
            {
                "system_id": system_id,
                "judge_id": judge_id,
                "metric_id": metric_id,
                "case_count": len(case_ids),
                "samples": samples,
                "seed": suite.statistics.bootstrap_seed,
                "confidence_level": suite.statistics.confidence_level,
                "observed": _round(observed),
                "ci_low": _round(
                    _percentile_value(
                        sampled_values,
                        low_pct,
                        fallback=observed,
                    )
                ),
                "ci_high": _round(
                    _percentile_value(
                        sampled_values,
                        high_pct,
                        fallback=observed,
                    )
                ),
            }
        )
    output.extend(
        _directional_bootstrap_intervals(
            suite=suite,
            reduced_rows=reduced_rows,
        )
    )
    return output


def paired_system_deltas(
    *,
    suite: EvaluationSuite,
    reduced_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    samples = suite.statistics.bootstrap_samples
    low_pct, high_pct = _confidence_bounds(suite.statistics.confidence_level)
    output: list[dict[str, Any]] = []
    by_system: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in reduced_rows:
        if not row.get("complete"):
            continue
        for metric_id, value in (row.get("metrics") or {}).items():
            by_system[
                (str(row["system_id"]), str(row["judge_id"]), str(metric_id))
            ][str(row["case_id"])].append(float(value))
    judge_ids = sorted({str(row["judge_id"]) for row in reduced_rows})
    directional_rows: dict[
        tuple[str, str],
        dict[tuple[str, str], dict[str, Any]],
    ] = defaultdict(dict)
    for row in reduced_rows:
        if row.get("complete") and row.get("directional_counts"):
            directional_rows[(str(row["system_id"]), str(row["judge_id"]))][
                (str(row["case_id"]), str(row["sample_id"]))
            ] = row
    for comparison in suite.comparisons:
        for judge_id in judge_ids:
            for metric_id in comparison.metric_ids:
                directional_selector = _directional_metric_selector(metric_id)
                if directional_selector is not None:
                    artifact_kind, selected_metric = directional_selector
                    left_rows = directional_rows.get(
                        (comparison.left_system_id, judge_id),
                        {},
                    )
                    right_rows = directional_rows.get(
                        (comparison.right_system_id, judge_id),
                        {},
                    )
                    shared_keys = sorted(set(left_rows) & set(right_rows))
                    if not shared_keys:
                        continue

                    def directional_delta(
                        keys: list[tuple[str, str]],
                    ) -> float:
                        left_score = _directional_micro_metrics(
                            [left_rows[key] for key in keys],
                            artifact_kind=artifact_kind,
                        )
                        right_score = _directional_micro_metrics(
                            [right_rows[key] for key in keys],
                            artifact_kind=artifact_kind,
                        )
                        return float(right_score[selected_metric]) - float(
                            left_score[selected_metric]
                        )

                    observed = directional_delta(shared_keys)
                    by_case: dict[str, list[tuple[str, str]]] = defaultdict(list)
                    for key in shared_keys:
                        by_case[key[0]].append(key)
                    case_ids = sorted(by_case)
                    rng = random.Random(
                        _stable_seed(
                            suite.statistics.bootstrap_seed,
                            comparison.comparison_id,
                            judge_id,
                            metric_id,
                        )
                    )
                    sampled: list[float] = []
                    for _ in range(samples):
                        sampled_keys: list[tuple[str, str]] = []
                        for _slot in case_ids:
                            case_id = rng.choice(case_ids)
                            candidates = by_case[case_id]
                            sampled_keys.extend(
                                rng.choice(candidates)
                                for _candidate_slot in candidates
                            )
                        sampled.append(directional_delta(sampled_keys))
                    row = {
                        "comparison_id": comparison.comparison_id,
                        "left_system_id": comparison.left_system_id,
                        "right_system_id": comparison.right_system_id,
                        "judge_id": judge_id,
                        "metric_id": metric_id,
                        "shared_case_count": len(case_ids),
                        "paired_candidate_count": len(shared_keys),
                        "delta": _round(observed),
                    }
                    if sampled:
                        row.update(
                            {
                                "samples": samples,
                                "seed": suite.statistics.bootstrap_seed,
                                "confidence_level": suite.statistics.confidence_level,
                                "ci_low": _round(
                                    _percentile_value(
                                        sampled,
                                        low_pct,
                                        fallback=observed,
                                    )
                                ),
                                "ci_high": _round(
                                    _percentile_value(
                                        sampled,
                                        high_pct,
                                        fallback=observed,
                                    )
                                ),
                            }
                        )
                    output.append(row)
                    continue
                left = by_system.get(
                    (comparison.left_system_id, judge_id, metric_id),
                    {},
                )
                right = by_system.get(
                    (comparison.right_system_id, judge_id, metric_id),
                    {},
                )
                shared_cases = sorted(set(left) & set(right))
                if not shared_cases:
                    continue
                case_deltas = {
                    case_id: statistics.mean(right[case_id])
                    - statistics.mean(left[case_id])
                    for case_id in shared_cases
                }
                observed = statistics.mean(case_deltas.values())
                rng = random.Random(
                    _stable_seed(
                        suite.statistics.bootstrap_seed,
                        comparison.comparison_id,
                        judge_id,
                        metric_id,
                    )
                )
                sampled = [
                    statistics.mean(
                        case_deltas[rng.choice(shared_cases)]
                        for _slot in shared_cases
                    )
                    for _ in range(samples)
                ] if samples > 0 else []
                row: dict[str, Any] = {
                    "comparison_id": comparison.comparison_id,
                    "left_system_id": comparison.left_system_id,
                    "right_system_id": comparison.right_system_id,
                    "judge_id": judge_id,
                    "metric_id": metric_id,
                    "shared_case_count": len(shared_cases),
                    "delta": _round(observed),
                }
                if sampled:
                    row.update(
                        {
                            "samples": samples,
                            "seed": suite.statistics.bootstrap_seed,
                            "confidence_level": suite.statistics.confidence_level,
                            "ci_low": _round(
                                _percentile_value(
                                    sampled,
                                    low_pct,
                                    fallback=observed,
                                )
                            ),
                            "ci_high": _round(
                                _percentile_value(
                                    sampled,
                                    high_pct,
                                    fallback=observed,
                                )
                            ),
                        }
                    )
                output.append(row)
    return output


def _claim_observed_value(
    claim: EvaluationClaim,
    *,
    summaries: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
) -> float | int | None:
    if claim.system_id is not None:
        candidates = [
            row
            for row in summaries
            if row["system_id"] == claim.system_id
            and (
                claim.judge_id is None
                or row["judge_id"] == claim.judge_id
            )
        ]
        if not candidates:
            return None
        row = candidates[0]
        if claim.metric_id in {
            "candidate_count",
            "complete_candidate_count",
            "failed_candidate_count",
            "case_count",
        }:
            return int(row[claim.metric_id])
        directional = row.get("directional_aggregate") or {}
        if claim.metric_id in directional:
            return directional[claim.metric_id]
        if claim.metric_id.startswith("median_"):
            metric_id = claim.metric_id.removeprefix("median_")
            metric = (row.get("metrics") or {}).get(metric_id) or {}
            return metric.get("median")
        if "_" in claim.metric_id:
            kind, _, metric_id = claim.metric_id.partition("_")
            by_kind = row.get("directional_by_kind") or {}
            kind_summary = by_kind.get(
                {
                    "entity": "entities",
                    "attribute": "attributes",
                    "relationship": "relationships",
                    "identifier": "identifiers",
                }.get(kind, kind)
            ) or {}
            if metric_id in kind_summary:
                return kind_summary[metric_id]
        metric = (row.get("metrics") or {}).get(claim.metric_id) or {}
        return metric.get("mean")
    candidates = [
        row
        for row in comparisons
        if row["comparison_id"] == claim.comparison_id
        and row["metric_id"] == claim.metric_id
        and (
            claim.judge_id is None
            or row["judge_id"] == claim.judge_id
        )
    ]
    return candidates[0]["delta"] if candidates else None


def compare_claims(
    *,
    claims: EvaluationClaimsManifest | None,
    summaries: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    archived_authoritative: bool,
    complete: bool,
) -> list[dict[str, Any]]:
    if claims is None:
        return []
    output: list[dict[str, Any]] = []
    for claim in claims.expanded_claims():
        observed = _claim_observed_value(
            claim,
            summaries=summaries,
            comparisons=comparisons,
        )
        status = "not_comparable"
        expected: float | int | None = (
            claim.expected_value
            if claim.expected_value is not None
            else claim.expected_count
        )
        if not complete:
            status = "incomplete"
        elif observed is not None and expected is not None:
            difference = abs(float(observed) - float(expected))
            if difference <= claim.tolerance:
                status = "matched"
            elif (
                claim.display_decimals is not None
                and round(float(observed), claim.display_decimals)
                == round(float(expected), claim.display_decimals)
            ):
                status = "within_reported_rounding"
            else:
                status = "different"
        output.append(
            {
                "claim_id": claim.claim_id,
                "report_reference": claim.report_reference,
                "system_id": claim.system_id,
                "comparison_id": claim.comparison_id,
                "judge_id": claim.judge_id,
                "metric_id": claim.metric_id,
                "expected": expected,
                "observed": observed,
                "difference": (
                    _round(float(observed) - float(expected))
                    if observed is not None and expected is not None
                    else None
                ),
                "status": status,
                "authoritative": archived_authoritative,
            }
        )
    return output


def _flatten_rows(rows: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    flattened: list[dict[str, Any]] = []
    fields: set[str] = set()
    for row in rows:
        output: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    if isinstance(nested_value, dict):
                        for leaf_key, leaf_value in nested_value.items():
                            output[f"{key}.{nested_key}.{leaf_key}"] = leaf_value
                    else:
                        output[f"{key}.{nested_key}"] = nested_value
            elif isinstance(value, list):
                output[key] = ";".join(str(item) for item in value)
            else:
                output[key] = value
        fields.update(output)
        flattened.append(output)
    return sorted(fields), flattened


def write_csv_report(path: Path, rows: list[dict[str, Any]]) -> None:
    fields, flattened = _flatten_rows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flattened)


def _markdown_table(rows: list[dict[str, Any]], fields: list[str]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        values = [
            str(row.get(field, "")).replace("|", "\\|").replace("\n", " ")
            for field in fields
        ]
        lines.append("| " + " | ".join(values) + " |")
    return lines


def write_markdown_report(
    path: Path,
    *,
    suite_id: str,
    mode: str,
    summaries: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    accounting: dict[str, Any],
) -> None:
    summary_rows: list[dict[str, Any]] = []
    for summary in summaries:
        base = {
            "system": summary["system_id"],
            "judge": summary["judge_id"],
            "complete": (
                f"{summary['complete_candidate_count']}/{summary['candidate_count']}"
            ),
        }
        directional = summary.get("directional_aggregate") or {}
        for metric_id in ("micro_precision", "micro_recall", "micro_f1"):
            if metric_id in directional:
                base[metric_id] = directional[metric_id]
        for metric_id, value in (summary.get("metrics") or {}).items():
            base[metric_id] = value.get("mean")
        summary_rows.append(base)
    summary_fields = sorted(
        {key for row in summary_rows for key in row},
        key=lambda value: (value not in {"system", "judge", "complete"}, value),
    )
    lines = [
        f"# Evaluation report: {suite_id}",
        "",
        f"- Mode: `{mode}`",
        f"- Failures: {len(failures)}",
        f"- Generator jobs: {accounting.get('completed_generator_jobs', 0)}/"
        f"{accounting.get('planned_generator_jobs', 0)}",
        f"- Judge jobs: {accounting.get('completed_judge_jobs', 0)}/"
        f"{accounting.get('planned_judge_jobs', 0)}",
        "",
        "## System summaries",
        "",
        *_markdown_table(summary_rows, summary_fields),
        "",
        "## Paired comparisons",
        "",
        *_markdown_table(
            comparisons,
            [
                "comparison_id",
                "metric_id",
                "shared_case_count",
                "delta",
                "ci_low",
                "ci_high",
            ],
        ),
        "",
        "## Expected-value comparisons",
        "",
        *_markdown_table(
            claims,
            [
                "claim_id",
                "metric_id",
                "expected",
                "observed",
                "status",
                "authoritative",
            ],
        ),
        "",
    ]
    if mode in {"live", "rejudge"}:
        lines.extend(
            [
                "> Live generation and/or judging is nondeterministic. "
                "Numerical differences are reported rather than "
                "treated as artifact corruption.",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_reports(
    *,
    output_dir: Path,
    suite: EvaluationSuite,
    mode: str,
    raw_results: list[JudgeResultRecord],
    reduced_rows: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    bootstrap: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    accounting: dict[str, Any],
) -> None:
    raw_payload = [row.model_dump(mode="json") for row in raw_results]
    write_json_atomic(
        output_dir / "report.json",
        {
            "artifact_kind": "evaluation_report",
            "schema_version": 1,
            "suite_id": suite.suite_id,
            "mode": mode,
            "summaries": summaries,
            "bootstrap_intervals": bootstrap,
            "paired_deltas": comparisons,
            "claims": claims,
            "failures": failures,
            "accounting": accounting,
        },
    )
    write_json_atomic(output_dir / "raw_judge_results.json", raw_payload)
    write_json_atomic(output_dir / "candidate_scores.json", reduced_rows)
    write_json_atomic(output_dir / "system_summary.json", summaries)
    write_json_atomic(output_dir / "bootstrap_intervals.json", bootstrap)
    write_json_atomic(output_dir / "paired_deltas.json", comparisons)
    write_json_atomic(output_dir / "failures.json", failures)
    write_json_atomic(output_dir / "accounting.json", accounting)
    write_json_atomic(output_dir / "claim_comparison.json", claims)
    write_csv_report(output_dir / "raw_judge_results.csv", raw_payload)
    write_csv_report(output_dir / "candidate_scores.csv", reduced_rows)
    write_csv_report(output_dir / "system_summary.csv", summaries)
    write_csv_report(output_dir / "paired_deltas.csv", comparisons)
    write_csv_report(output_dir / "claim_comparison.csv", claims)
    write_markdown_report(
        output_dir / "report.md",
        suite_id=suite.suite_id,
        mode=mode,
        summaries=summaries,
        comparisons=comparisons,
        claims=claims,
        failures=failures,
        accounting=accounting,
    )
    write_markdown_report(
        output_dir / "claim_comparison.md",
        suite_id=suite.suite_id,
        mode=mode,
        summaries=[],
        comparisons=[],
        claims=claims,
        failures=failures,
        accounting=accounting,
    )


__all__ = [
    "EvaluationReportError",
    "bootstrap_intervals",
    "compare_claims",
    "paired_system_deltas",
    "reduce_judge_results",
    "summarize_systems",
    "validate_result_metrics",
    "write_reports",
]
