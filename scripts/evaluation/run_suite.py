from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from core.runtime_env import load_dotenv_file
from judge.evaluation_artifacts import (
    stable_file_bytes,
    verify_materialized_artifact,
    write_json_atomic,
)
from judge.evaluation_contracts import (
    CandidateRecord,
    EvaluationCandidateManifest,
    EvaluationClaimsManifest,
    JudgeResultRecord,
)
from judge.evaluation_reporting import (
    bootstrap_intervals,
    compare_claims,
    paired_system_deltas,
    reduce_judge_results,
    summarize_systems,
    write_reports,
)
from scripts.evaluation.suite_adapters import (
    EvaluationAdapterError,
    execute_generation_sources,
    execute_judges,
    preflight_suite,
    safe_evaluation_error,
)
from scripts.evaluation.suite_workspace import (
    EvaluationWorkspaceError,
    complete_stage,
    load_run_state,
    load_suite,
    prepare_workspace,
    stage_is_resumable,
    update_run_state,
)


class EvaluationRunError(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a versioned, self-contained evaluation suite without starting "
            "the application server."
        )
    )
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    return parser


def _load_json(path: Path, *, label: str) -> Any:
    payload = stable_file_bytes(path, label=label)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationRunError(f"{label} is not valid UTF-8 JSON") from exc


def _load_candidates(work_dir: Path) -> list[dict[str, Any]]:
    manifest = EvaluationCandidateManifest.model_validate(
        _load_json(
            work_dir / "candidate_manifest.json",
            label="evaluation candidate manifest",
        )
    )
    rows = [row.model_dump(mode="json") for row in manifest.candidates]
    for row in manifest.candidates:
        for artifact in row.artifacts.values():
            verify_materialized_artifact(artifact, work_dir=work_dir)
    return rows


def _load_results(work_dir: Path) -> list[JudgeResultRecord]:
    payload = _load_json(
        work_dir / "judge_results.json",
        label="evaluation judge-result manifest",
    )
    if not isinstance(payload, dict) or payload.get("artifact_kind") != (
        "evaluation_judge_result_manifest"
    ):
        raise EvaluationRunError("evaluation judge-result manifest is invalid")
    rows = payload.get("results")
    if not isinstance(rows, list):
        raise EvaluationRunError("evaluation judge-result manifest has no results")
    return [JudgeResultRecord.model_validate(row) for row in rows]


def _usage_totals(
    *,
    candidates: list[dict[str, Any]],
    results: list[JudgeResultRecord],
) -> dict[str, Any]:
    generation_usage: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in candidates:
        usage = row.get("usage")
        if not isinstance(usage, dict):
            continue
        provenance = row.get("generator_provenance")
        source_id = (
            str(provenance.get("source_id"))
            if isinstance(provenance, dict) and provenance.get("source_id")
            else str(row["system_id"])
        )
        key = (source_id, str(row["case_id"]), str(row["sample_id"]))
        existing = generation_usage.get(key)
        if existing is not None and existing != usage:
            raise EvaluationRunError(
                "candidate views from one generation job report conflicting usage"
            )
        generation_usage[key] = usage
    usage_records = [
        *generation_usage.values(),
        *(row.usage for row in results if isinstance(row.usage, dict)),
    ]

    def summed(*keys: str) -> int:
        total = 0
        for usage in usage_records:
            for key in keys:
                value = usage.get(key)
                if isinstance(value, (int, float)):
                    total += int(value)
                    break
        return total

    def summed_float(*keys: str) -> float:
        total = 0.0
        for usage in usage_records:
            for key in keys:
                value = usage.get(key)
                if isinstance(value, (int, float)):
                    total += float(value)
                    break
        return round(total, 6)

    return {
        "usage_records": len(usage_records),
        "provider_calls": summed("calls"),
        "input_tokens": summed("input_tokens", "prompt_tokens"),
        "output_tokens": summed("output_tokens", "completion_tokens"),
        "total_tokens": summed("total_tokens"),
        "operation_seconds": summed_float(
            "duration_seconds",
            "elapsed_seconds",
        ),
    }


def _completed_generator_jobs(
    *,
    suite: Any,
    candidates: list[dict[str, Any]],
) -> int:
    generated_source_ids = {
        source.source_id
        for source in suite.generation_sources
        if source.kind in {"catalog_harness", "command"}
    }
    completed: set[tuple[str, str, str]] = set()
    for row in candidates:
        provenance = row.get("generator_provenance")
        if not isinstance(provenance, dict):
            continue
        source_id = str(provenance.get("source_id") or "")
        if source_id not in generated_source_ids:
            continue
        completed.add(
            (
                source_id,
                str(row["case_id"]),
                str(row["sample_id"]),
            )
        )
    return len(completed)


def _failures_from_file(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = _load_json(path, label="evaluation failure manifest")
    return payload if isinstance(payload, list) else []


def _verify_preflight_adapter_identities(
    *,
    work_dir: Path,
    preflight: dict[str, Any],
) -> None:
    path = work_dir / "preflight.json"
    if not path.is_file():
        return
    previous = _load_json(path, label="prior evaluation preflight")
    if not isinstance(previous, dict):
        raise EvaluationRunError("prior evaluation preflight is invalid")
    if previous.get("adapter_identities") != preflight.get(
        "adapter_identities"
    ):
        raise EvaluationRunError(
            "adapter executable identity conflicts with the resumable "
            "evaluation workspace"
        )


async def run(args: argparse.Namespace) -> int:
    load_dotenv_file()
    suite_path = Path(args.suite).absolute()
    suite = load_suite(suite_path)
    mode = str(suite.metadata.get("reproduction_level") or "general")
    started = time.monotonic()
    prepared = prepare_workspace(
        suite=suite,
        suite_path=suite_path,
        work_dir=args.work_dir,
        resume=args.resume,
        mode=mode,
    )
    state = load_run_state(args.work_dir)

    if bool(state.get("completed")) and stage_is_resumable(
        work_dir=args.work_dir,
        state=state,
        stage_name="reporting",
    ):
        print(
            f"Evaluation suite {suite.suite_id!r} is already complete; "
            f"verified resumable reports in {args.work_dir / 'reports'}."
        )
        return 0
    preflight = await asyncio.to_thread(
        preflight_suite,
        suite=suite,
        prepared=prepared,
    )
    _verify_preflight_adapter_identities(
        work_dir=args.work_dir,
        preflight=preflight,
    )
    write_json_atomic(args.work_dir / "preflight.json", preflight)
    complete_stage(
        work_dir=args.work_dir,
        state=state,
        stage_name="preflight",
        relative_outputs=[
            "preflight.json",
        ],
    )
    if args.validate_only:
        state["status"] = "validated"
        update_run_state(args.work_dir, state)
        print(
            f"Evaluation suite {suite.suite_id!r} passed complete preflight; "
            "no generator or judge calls were made."
        )
        return 0

    generation_failures_path = args.work_dir / "generation_failures.json"
    if stage_is_resumable(
        work_dir=args.work_dir,
        state=state,
        stage_name="generation",
    ):
        candidates = _load_candidates(args.work_dir)
        generation_failures = _failures_from_file(generation_failures_path)
    else:
        candidates, generation_failures = await execute_generation_sources(
            suite=suite,
            prepared=prepared,
            work_dir=args.work_dir,
            resume=args.resume,
            keep_going=args.keep_going,
        )
        manifest = EvaluationCandidateManifest(
            candidates=[CandidateRecord.model_validate(row) for row in candidates]
        )
        write_json_atomic(
            args.work_dir / "candidate_manifest.json",
            manifest.model_dump(mode="json"),
        )
        write_json_atomic(generation_failures_path, generation_failures)
        complete_stage(
            work_dir=args.work_dir,
            state=state,
            stage_name="generation",
            relative_outputs=[
                "candidate_manifest.json",
                "generation_failures.json",
            ],
        )

    judging_failures_path = args.work_dir / "judging_failures.json"
    if stage_is_resumable(
        work_dir=args.work_dir,
        state=state,
        stage_name="judging",
    ):
        results = _load_results(args.work_dir)
        judging_failures = _failures_from_file(judging_failures_path)
    else:
        results, judging_failures = await execute_judges(
            suite=suite,
            prepared=prepared,
            candidates=candidates,
            work_dir=args.work_dir,
            keep_going=args.keep_going,
        )
        write_json_atomic(
            args.work_dir / "judge_results.json",
            {
                "artifact_kind": "evaluation_judge_result_manifest",
                "schema_version": 1,
                "results": [row.model_dump(mode="json") for row in results],
            },
        )
        write_json_atomic(judging_failures_path, judging_failures)
        complete_stage(
            work_dir=args.work_dir,
            state=state,
            stage_name="judging",
            relative_outputs=[
                "judge_results.json",
                "judging_failures.json",
            ],
        )

    failures = [*generation_failures, *judging_failures]
    reduced = reduce_judge_results(
        suite=suite,
        candidates=candidates,
        results=results,
    )
    summaries = summarize_systems(reduced)
    bootstrap = bootstrap_intervals(suite=suite, reduced_rows=reduced)
    comparisons = paired_system_deltas(suite=suite, reduced_rows=reduced)
    complete = not failures and all(row.get("complete") for row in reduced)
    claims_manifest = (
        EvaluationClaimsManifest.model_validate(prepared["claims"])
        if prepared.get("claims")
        else None
    )
    claim_rows = compare_claims(
        claims=claims_manifest,
        summaries=summaries,
        comparisons=comparisons,
        archived_authoritative=mode == "archived",
        complete=complete,
    )
    plan = prepared["plan"]
    accounting = {
        **plan,
        "completed_generator_jobs": min(
            plan["planned_generator_jobs"],
            _completed_generator_jobs(
                suite=suite,
                candidates=candidates,
            ),
        ),
        "completed_candidates": len(candidates),
        "completed_judge_jobs": sum(
            1 for result in results if result.status == "completed"
        ),
        "failed_judge_jobs": sum(
            1 for result in results if result.status != "completed"
        ),
        "wall_seconds": round(time.monotonic() - started, 6),
        **_usage_totals(candidates=candidates, results=results),
    }
    report_dir = args.work_dir / "reports"
    write_reports(
        output_dir=report_dir,
        suite=suite,
        mode=mode,
        raw_results=results,
        reduced_rows=reduced,
        summaries=summaries,
        bootstrap=bootstrap,
        comparisons=comparisons,
        claims=claim_rows,
        failures=failures,
        accounting=accounting,
    )
    report_outputs = [
        path.relative_to(args.work_dir).as_posix()
        for path in sorted(report_dir.iterdir())
        if path.is_file()
    ]
    complete_stage(
        work_dir=args.work_dir,
        state=state,
        stage_name="reporting",
        relative_outputs=report_outputs,
    )
    state["status"] = "completed" if complete else "incomplete"
    state["completed"] = complete
    state["numerical_claims_authoritative"] = mode == "archived"
    update_run_state(args.work_dir, state)
    print(
        f"Evaluation suite {suite.suite_id!r} wrote {len(candidates)} candidates, "
        f"{len(results)} judge results, and reports to {report_dir}."
    )
    if mode in {"live", "rejudge"}:
        print(
            "Live model results are nondeterministic; repeated runs may "
            "produce different numerical results."
        )
    return 0 if complete else 1


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        return asyncio.run(run(args))
    except (
        EvaluationRunError,
        EvaluationAdapterError,
        EvaluationWorkspaceError,
        ValueError,
        OSError,
    ) as exc:
        print(
            "evaluation suite failed: "
            + safe_evaluation_error(exc, work_dir=args.work_dir),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
