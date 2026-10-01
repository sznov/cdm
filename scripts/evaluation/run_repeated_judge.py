from __future__ import annotations

import argparse
import concurrent.futures
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from core.artifacts import load_json, read_checkpoint_manifest_path, write_json
from core.providers.factory import default_model_for_provider
from judge import (
    DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE,
    DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS,
    build_repeated_judge_reports,
    degenerate_zero_directional_reason,
    normalize_model_rows,
    write_repeated_judge_reports,
)


def evaluation_path(output_dir: Path, row: dict[str, Any], repeat_index: int) -> Path:
    return (
        output_dir
        / "evals"
        / str(row["spec_id"]).zfill(3)
        / str(row.get("generation_run_id") or "gen-001")
        / str(row.get("checkpoint_label") or "checkpoint")
        / f"judge_{repeat_index:03d}"
        / "evaluation.json"
    )


def format_command(template: str, row: dict[str, Any], eval_dir: Path, args: argparse.Namespace) -> list[str]:
    values = {
        "gold_path": row["gold_path"],
        "model_path": row["model_path"],
        "spec_path": row["spec_path"],
        "eval_dir": str(eval_dir),
        "evaluation_path": str(eval_dir / "evaluation.json"),
        "spec_id": row["spec_id"],
        "generation_run_id": row["generation_run_id"],
        "checkpoint_label": row["checkpoint_label"],
        "judge_model": args.judge_model,
        "judge_provider": args.judge_provider,
        "judge_prompt_profile": args.judge_prompt_profile,
        "codex_reasoning_effort": args.codex_reasoning_effort,
        "timeout_seconds": args.timeout_seconds,
    }
    return shlex.split(template.format(**values))


def _same_path(left: Any, right: Any) -> bool:
    if left in (None, "") or right in (None, ""):
        return str(left or "") == str(right or "")
    return Path(str(left)) == Path(str(right))


def existing_evaluation_matches_row(eval_path: Path, row: dict[str, Any], args: argparse.Namespace) -> bool:
    try:
        payload = load_json(eval_path)
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    if not _same_path(payload.get("gold_model_path"), row.get("gold_path")):
        return False
    if not _same_path(payload.get("predicted_model_path"), row.get("model_path")):
        return False
    if not _same_path(payload.get("specification_path"), row.get("spec_path")):
        return False
    if payload.get("judge_prompt_profile") != args.judge_prompt_profile:
        return False
    judge_model = payload.get("judge_model")
    if judge_model and args.judge_model and str(judge_model) != str(args.judge_model):
        return False
    return True


def run_one(row: dict[str, Any], repeat_index: int, args: argparse.Namespace) -> dict[str, Any]:
    eval_path = evaluation_path(args.output_dir, row, repeat_index)
    eval_dir = eval_path.parent
    status_path = eval_dir / "eval_status.json"
    if eval_path.exists() and not args.force:
        degenerate_reason = degenerate_zero_directional_reason(eval_path)
        cache_mismatch = not existing_evaluation_matches_row(eval_path, row, args)
        if (degenerate_reason or cache_mismatch) and not args.collect_only:
            try:
                eval_path.unlink()
            except OSError:
                pass
        else:
            status = "failed" if degenerate_reason else "completed"
            result = {
                "model_key": row["model_key"],
                "spec_id": row["spec_id"],
                "generation_run_id": row["generation_run_id"],
                "checkpoint_label": row["checkpoint_label"],
                "repeat_index": repeat_index,
                "status": status,
                "skipped": not degenerate_reason and not cache_mismatch,
                "eval_dir": str(eval_dir),
                "evaluation_path": str(eval_path),
                "degenerate_reason": degenerate_reason,
                "cache_mismatch": cache_mismatch,
            }
            write_json(status_path, result)
            return result
    if args.collect_only:
        return {
            "model_key": row["model_key"],
            "spec_id": row["spec_id"],
            "generation_run_id": row["generation_run_id"],
            "checkpoint_label": row["checkpoint_label"],
            "repeat_index": repeat_index,
            "status": "missing",
            "error": "evaluation.json does not exist and --collect-only was used",
            "eval_dir": str(eval_dir),
            "evaluation_path": str(eval_path),
        }

    eval_dir.mkdir(parents=True, exist_ok=True)
    cmd = format_command(args.judge_command, row, eval_dir, args)
    attempts: list[dict[str, Any]] = []
    total_started = time.monotonic()
    result: dict[str, Any] | None = None
    for attempt_index in range(1, max(1, args.max_attempts) + 1):
        started = time.monotonic()
        degenerate_reason = ""
        try:
            proc = subprocess.run(
                cmd,
                cwd=args.cwd,
                text=True,
                capture_output=True,
                timeout=args.timeout_seconds,
            )
            status = "completed" if proc.returncode == 0 and eval_path.exists() else "failed"
            degenerate_reason = ""
            if status == "completed":
                degenerate_reason = degenerate_zero_directional_reason(eval_path)
                if degenerate_reason:
                    status = "failed"
            attempt = {
                "attempt_index": attempt_index,
                "status": status,
                "returncode": proc.returncode,
                "seconds": round(time.monotonic() - started, 3),
                "stdout": proc.stdout[-8000:],
                "stderr": proc.stderr[-8000:],
                "evaluation_path": str(eval_path) if eval_path.exists() else None,
                "degenerate_reason": degenerate_reason,
            }
        except subprocess.TimeoutExpired as exc:
            attempt = {
                "attempt_index": attempt_index,
                "status": "timeout",
                "seconds": round(time.monotonic() - started, 3),
                "stdout": (exc.stdout or "")[-8000:] if isinstance(exc.stdout, str) else "",
                "stderr": (exc.stderr or "")[-8000:] if isinstance(exc.stderr, str) else "",
                "evaluation_path": None,
                "degenerate_reason": "",
            }
            status = "timeout"
        attempts.append(attempt)
        result = {
            "model_key": row["model_key"],
            "spec_id": row["spec_id"],
            "generation_run_id": row["generation_run_id"],
            "checkpoint_label": row["checkpoint_label"],
            "repeat_index": repeat_index,
            "status": status,
            "seconds": round(time.monotonic() - total_started, 3),
            "cmd": cmd,
            "eval_dir": str(eval_dir),
            "evaluation_path": str(eval_path) if eval_path.exists() else None,
            "attempt_index": attempt_index,
            "retry_index": attempt_index - 1,
            "attempts": attempts,
            "stdout": attempt.get("stdout"),
            "stderr": attempt.get("stderr"),
            "returncode": attempt.get("returncode"),
            "degenerate_reason": degenerate_reason,
        }
        if status == "completed":
            break
        if degenerate_reason and attempt_index < max(1, args.max_attempts) and eval_path.exists():
            try:
                eval_path.unlink()
            except OSError:
                pass
        if attempt_index < max(1, args.max_attempts):
            time.sleep(min(10.0, 2.0 * attempt_index))
    assert result is not None
    write_json(status_path, result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or collect repeated directional judge outputs for checkpoint rows.")
    parser.add_argument("--checkpoint-manifest", required=True, type=Path)
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
    parser.add_argument(
        "--judge-command",
        default=(
            "python -m scripts.evaluation.evaluate_structured_model "
            "--gold {gold_path} --predicted {model_path} --spec {spec_path} "
            "--output-dir {eval_dir} --provider {judge_provider} --model {judge_model} "
            "--judge-prompt-profile {judge_prompt_profile} "
            "--codex-reasoning-effort {codex_reasoning_effort} --timeout-seconds {timeout_seconds}"
        ),
        help=(
            "Optional command template. Placeholders: {gold_path}, {model_path}, {spec_path}, "
            "{eval_dir}, {evaluation_path}, {spec_id}, {generation_run_id}, {checkpoint_label}, "
            "{judge_model}, {judge_provider}, {judge_prompt_profile}, {codex_reasoning_effort}, {timeout_seconds}."
        ),
    )
    parser.add_argument("--collect-only", action="store_true", help="Only aggregate existing evaluation.json files; do not run missing judges.")
    parser.add_argument("--cwd", type=Path, default=Path("."))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.judge_model:
        args.judge_model = default_model_for_provider(args.judge_provider)
    model_rows = load_checkpoint_rows(args.checkpoint_manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "selected_checkpoints.json", model_rows)

    jobs = [(row, repeat_index) for row in model_rows for repeat_index in range(1, args.judge_repeats + 1)]
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = [pool.submit(run_one, row, repeat_index, args) for row, repeat_index in jobs]
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"status": "exception", "error": str(exc)})
            write_json(args.output_dir / "judge_run_manifest.json", sorted(results, key=lambda item: str(item.get("eval_dir") or item.get("error") or "")))

    reports = build_repeated_judge_reports(
        model_rows,
        results,
        judge_repeats=args.judge_repeats,
        judge_model=args.judge_model,
        judge_provider=args.judge_provider,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    write_repeated_judge_reports(args.output_dir, reports)
    completed = sum(1 for result in results if result.get("status") == "completed")
    print(f"Wrote repeated judge reports for {len(model_rows)} checkpoints; {completed}/{len(jobs)} judge runs completed.")
    return 0 if completed == len(jobs) else 1


def load_checkpoint_rows(path: Path) -> list[dict[str, Any]]:
    """Validate the persisted boundary before applying judge workflow defaults."""

    return normalize_model_rows(read_checkpoint_manifest_path(path))


if __name__ == "__main__":
    raise SystemExit(main())
