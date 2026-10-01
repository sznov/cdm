from __future__ import annotations

import argparse
import concurrent.futures
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from core.artifacts import load_json, write_json
from core.providers.factory import default_model_for_provider
from judge import (
    DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE,
    DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS,
    build_repeated_judge_reports,
    normalize_model_rows,
    write_repeated_judge_reports,
)
from scripts.evaluation.run_repeated_judge import run_one


def snapshot_rows_to_model_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if not all((row.get("spec_id"), row.get("model_path"), row.get("gold_path"), row.get("spec_path"))):
            continue
        converted = dict(row)
        converted["checkpoint_label"] = str(row.get("snapshot_id") or row.get("checkpoint_label") or "snapshot")
        converted["source_snapshot_id"] = row.get("snapshot_id")
        converted["source_snapshot_index"] = row.get("snapshot_index")
        candidates.append(converted)
    return normalize_model_rows(candidates)


def build_repeated_args(args: argparse.Namespace) -> SimpleNamespace:
    judge_model = args.judge_model or default_model_for_provider(args.judge_provider)
    judge_command = (
        "python -m scripts.evaluation.evaluate_structured_model "
        "--gold {gold_path} --predicted {model_path} --spec {spec_path} "
        "--output-dir {eval_dir} --provider {judge_provider} --model {judge_model} "
        "--judge-prompt-profile {judge_prompt_profile} "
        "--codex-reasoning-effort {codex_reasoning_effort} --timeout-seconds {timeout_seconds}"
    )
    return SimpleNamespace(
        output_dir=args.output_dir,
        force=args.force,
        collect_only=args.collect_only,
        judge_command=judge_command,
        judge_model=judge_model,
        judge_provider=args.judge_provider,
        judge_prompt_profile=args.judge_prompt_profile,
        codex_reasoning_effort=args.codex_reasoning_effort,
        timeout_seconds=args.timeout_seconds,
        max_attempts=args.max_attempts,
        cwd=args.cwd,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Judge every exported snapshot and write trajectory reports.")
    parser.add_argument("--snapshot-manifest", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--judge-repeats", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--judge-provider", choices=("gemini", "codex", "nvidia_nim"), default="codex")
    parser.add_argument("--judge-model", help="Defaults to the selected provider's default model.")
    parser.add_argument(
        "--judge-prompt-profile",
        choices=DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS,
        default=DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE,
    )
    parser.add_argument("--codex-reasoning-effort", default="xhigh")
    parser.add_argument("--bootstrap-samples", type=int, default=0)
    parser.add_argument("--bootstrap-seed", type=int, default=20260523)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--cwd", type=Path, default=Path("."))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    raw_rows = load_json(args.snapshot_manifest)
    if not isinstance(raw_rows, list):
        raise SystemExit(f"Snapshot manifest must be a list: {args.snapshot_manifest}")
    model_rows = snapshot_rows_to_model_rows([row for row in raw_rows if isinstance(row, dict)])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "trajectory_checkpoints.json", model_rows)
    repeated_args = build_repeated_args(args)
    jobs = [(row, repeat_index) for row in model_rows for repeat_index in range(1, args.judge_repeats + 1)]
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = [pool.submit(run_one, row, repeat_index, repeated_args) for row, repeat_index in jobs]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"status": "exception", "error": str(exc)})
            write_json(
                args.output_dir / "trajectory_judge_manifest.json",
                sorted(results, key=lambda item: str(item.get("eval_dir") or item.get("error") or "")),
            )
    reports = build_repeated_judge_reports(
        model_rows,
        results,
        judge_repeats=args.judge_repeats,
        judge_model=repeated_args.judge_model,
        judge_provider=args.judge_provider,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    write_repeated_judge_reports(args.output_dir, reports)
    completed = sum(1 for result in results if result.get("status") == "completed")
    print(f"Wrote trajectory reports for {len(model_rows)} snapshots; {completed}/{len(jobs)} judge runs completed.")
    return 0 if completed == len(jobs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
