from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from core.artifacts import load_json, utc_now, write_json
from core.providers.factory import default_model_for_provider
from harnesses.catalog import get_harness_template
from judge import DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE, DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS
from judge.protocol_profiles import (
    direct_generation_profiles,
    harness_checkpoint_profiles,
    load_protocol_profile_config,
)


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"created_at_utc": utc_now(), "steps": []}
    payload = load_json(path)
    return payload if isinstance(payload, dict) else {"created_at_utc": utc_now(), "steps": []}


def step_completed(manifest: dict[str, Any], name: str) -> bool:
    steps = manifest.get("steps")
    if not isinstance(steps, list):
        return False
    return any(isinstance(step, dict) and step.get("name") == name and step.get("status") == "completed" for step in steps)


def upsert_step(manifest: dict[str, Any], row: dict[str, Any]) -> None:
    steps = manifest.setdefault("steps", [])
    if not isinstance(steps, list):
        manifest["steps"] = steps = []
    for index, step in enumerate(steps):
        if isinstance(step, dict) and step.get("name") == row.get("name"):
            steps[index] = row
            return
    steps.append(row)


def run_step(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    name: str,
    command: list[str],
    cwd: Path,
    resume: bool,
) -> int:
    if resume and step_completed(manifest, name):
        print(f"skip {name}: already completed")
        return 0
    started = utc_now()
    start = time.monotonic()
    proc = subprocess.run(command, cwd=cwd, text=True)
    row = {
        "name": name,
        "status": "completed" if proc.returncode == 0 else "failed",
        "command": command,
        "returncode": proc.returncode,
        "started_at_utc": started,
        "ended_at_utc": utc_now(),
        "duration_seconds": round(time.monotonic() - start, 3),
    }
    upsert_step(manifest, row)
    write_json(manifest_path, manifest)
    return proc.returncode


def python_cmd(*parts: str | Path) -> list[str]:
    return [sys.executable, "-m", *[str(part) for part in parts]]


def add_spec_ids(command: list[str], spec_ids: list[str]) -> list[str]:
    for spec_id in spec_ids:
        command.extend(["--spec-id", str(spec_id).zfill(3)])
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a reproducible generation/judging protocol from scriptable artifacts.")
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--spec-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    parser.add_argument("--spec-id", action="append", default=[])
    parser.add_argument("--generation-repeats", type=int)
    parser.add_argument("--judge-repeats", type=int)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--generation-max-attempts", type=int)
    parser.add_argument("--judge-max-attempts", type=int, default=2)
    parser.add_argument("--gemini-model")
    parser.add_argument("--judge-provider", choices=("gemini", "codex", "nvidia_nim"), default="codex")
    parser.add_argument("--judge-model")
    parser.add_argument("--judge-prompt-profile", choices=DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS)
    parser.add_argument("--codex-reasoning-effort", default="xhigh")
    parser.add_argument("--profile-config", type=Path)
    parser.add_argument("--include-optional-profiles", action="store_true")
    parser.add_argument("--bootstrap-samples", type=int, default=0)
    parser.add_argument("--bootstrap-seed", type=int, default=20260523)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--include-codex-reference", action="store_true")
    parser.add_argument("--skip-direct-baseline", action="store_true")
    parser.add_argument("--skip-harness", action="store_true")
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--evaluate-trajectory", action="store_true")
    parser.add_argument("--keep-going", action="store_true")
    return parser


def resolved_direct_generation_counts(profile: dict[str, Any], args: argparse.Namespace) -> tuple[int, int, int]:
    target_valid = int(
        args.generation_repeats
        if args.generation_repeats is not None
        else profile.get("target_valid_generations")
        or profile.get("generation_repeats")
        or 1
    )
    generation_repeats = int(
        args.generation_repeats
        if args.generation_repeats is not None
        else profile.get("generation_repeats")
        or target_valid
    )
    fill_max_attempts = int(profile.get("fill_max_attempts") or max(target_valid, generation_repeats))
    fill_max_attempts = max(fill_max_attempts, target_valid)
    return generation_repeats, target_valid, fill_max_attempts


def resolved_generation_repeats(args: argparse.Namespace) -> int:
    return int(args.generation_repeats if args.generation_repeats is not None else 5)


def resolved_generation_max_attempts(args: argparse.Namespace) -> int:
    return int(args.generation_max_attempts if args.generation_max_attempts is not None else 3)


def resolved_judge_repeats(profile: dict[str, Any], args: argparse.Namespace) -> int:
    return int(args.judge_repeats if args.judge_repeats is not None else profile.get("judge_repeats") or 5)


def resolved_judge_prompt_profile(profile: dict[str, Any], args: argparse.Namespace) -> str:
    return str(args.judge_prompt_profile or profile.get("judge_prompt_profile") or DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE)


def resolved_harness_judge_prompt_profile(profiles: list[dict[str, Any]], args: argparse.Namespace) -> str:
    resolved = sorted({resolved_judge_prompt_profile(profile, args) for profile in profiles})
    if not resolved:
        return DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE
    if len(resolved) > 1:
        raise ValueError(f"Harness checkpoint profiles must use one judge prompt profile per run, got: {', '.join(resolved)}")
    return resolved[0]


def direct_prompt_profile_id(profile: dict[str, Any]) -> str:
    harness_id = str(profile.get("harness_id") or "").strip()
    if harness_id:
        template = get_harness_template(harness_id)
        if isinstance(template, dict) and template.get("prompt_profile"):
            return str(template["prompt_profile"])
    return str(profile.get("prompt_profile") or "schema_only_v1")


def structured_patch_harness_id(profiles: list[dict[str, Any]]) -> str:
    ids = sorted({str(profile.get("harness_id") or "").strip() for profile in profiles if str(profile.get("harness_id") or "").strip()})
    return ids[0] if ids else "gemma4-tuned-final"


def main() -> int:
    args = build_parser().parse_args()
    app_dir = Path(__file__).resolve().parents[2]
    work_dir = args.work_dir
    work_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = work_dir / "protocol_manifest.json"
    manifest = load_manifest(manifest_path)
    gemini_model = args.gemini_model or default_model_for_provider("gemini")
    judge_model = args.judge_model or default_model_for_provider(args.judge_provider)
    profile_config = load_protocol_profile_config(args.profile_config)
    direct_profiles = direct_generation_profiles(profile_config)
    harness_profiles = harness_checkpoint_profiles(profile_config)

    failures = 0

    def step(name: str, command: list[str]) -> None:
        nonlocal failures
        code = run_step(manifest=manifest, manifest_path=manifest_path, name=name, command=command, cwd=app_dir, resume=args.resume)
        if code != 0:
            failures += 1
            if not args.keep_going:
                raise SystemExit(code)

    for profile in direct_profiles:
        profile_id = str(profile["id"])
        provider = str(profile.get("provider") or "gemini")
        if profile.get("optional") and not (args.include_optional_profiles or args.include_codex_reference):
            continue
        if args.skip_direct_baseline and provider != "codex":
            continue
        profile_model = str(profile.get("model") or (gemini_model if provider == "gemini" else default_model_for_provider(provider)))
        generation_repeats, target_valid, fill_max_attempts = resolved_direct_generation_counts(profile, args)
        manifest_rel = Path(str(profile.get("manifest") or f"{profile_id}/checkpoint_manifest.json"))
        output_dir = work_dir / manifest_rel.parent
        command = python_cmd(
            "scripts.generation.direct_baseline",
            "--provider",
            provider,
            "--model",
            profile_model,
            "--profile",
            str(profile.get("profile_arg") or profile_id),
            "--prompt-profile",
            direct_prompt_profile_id(profile),
            "--spec-dir",
            args.spec_dir,
            "--reference-dir",
            args.reference_dir,
            "--out-dir",
            output_dir,
            "--generation-repeats",
            str(generation_repeats),
            "--target-valid-generations",
            str(target_valid),
            "--fill-max-attempts",
            str(fill_max_attempts),
        )
        if provider == "codex":
            command.extend(["--codex-reasoning-effort", args.codex_reasoning_effort])
        step(f"{profile_id}_generation", add_spec_ids(command, args.spec_id))

    if not args.skip_harness:
        command = python_cmd(
            "scripts.generation.batch_harness",
            "--spec-dir",
            args.spec_dir,
            "--reference-dir",
            args.reference_dir,
            "--out-dir",
            work_dir / "harness_generation",
            "--generation-repeats",
            str(resolved_generation_repeats(args)),
            "--concurrency",
            str(args.concurrency),
            "--max-attempts",
            str(resolved_generation_max_attempts(args)),
            "--model",
            gemini_model,
            "--harness-id",
            structured_patch_harness_id(harness_profiles),
        )
        if args.resume:
            command.append("--resume")
        step("harness_generation", add_spec_ids(command, args.spec_id))

        step(
            "snapshot_export",
            python_cmd(
                "scripts.evaluation.export_snapshots",
                "--run",
                work_dir / "harness_generation",
                "--out-dir",
                work_dir / "snapshots",
                "--spec-dir",
                args.spec_dir,
                "--reference-dir",
                args.reference_dir,
            ),
        )
        step(
            "checkpoint_selection",
            python_cmd(
                "scripts.evaluation.select_protocol_checkpoints",
                "--snapshot-manifest",
                work_dir / "snapshots" / "snapshot_manifest.json",
                "--output",
                work_dir / "selected_checkpoints" / "checkpoint_manifest.json",
                "--csv-output",
                work_dir / "selected_checkpoints" / "checkpoint_manifest.csv",
            ),
        )
        step(
            "generation_accounting",
            python_cmd(
                "scripts.evaluation.collect_accounting",
                "--run",
                work_dir / "harness_generation",
                "--out-dir",
                work_dir / "accounting",
            ),
        )

    if not args.skip_judge:
        for profile in direct_profiles:
            profile_id = str(profile["id"])
            if profile.get("optional") and not (args.include_optional_profiles or args.include_codex_reference):
                continue
            if args.skip_direct_baseline and str(profile.get("provider") or "gemini") != "codex":
                continue
            manifest_rel = Path(str(profile.get("manifest") or f"{profile_id}/checkpoint_manifest.json"))
            judge_dir = work_dir / str(profile.get("judge_output_dir") or f"{profile_id}_repeated_judge")
            command = python_cmd(
                "scripts.evaluation.run_repeated_judge",
                "--checkpoint-manifest",
                work_dir / manifest_rel,
                "--output-dir",
                judge_dir,
                "--judge-repeats",
                str(resolved_judge_repeats(profile, args)),
                "--concurrency",
                str(args.concurrency),
                "--judge-provider",
                args.judge_provider,
                "--judge-model",
                judge_model,
                "--judge-prompt-profile",
                resolved_judge_prompt_profile(profile, args),
                "--codex-reasoning-effort",
                args.codex_reasoning_effort,
                "--max-attempts",
                str(args.judge_max_attempts),
            )
            if args.collect_only:
                command.append("--collect-only")
            step(f"{profile_id}_repeated_judge", command)

        if not args.skip_harness and harness_profiles:
            harness_judge_repeats = max(resolved_judge_repeats(profile, args) for profile in harness_profiles)
            command = python_cmd(
                "scripts.evaluation.run_repeated_judge",
                "--checkpoint-manifest",
                work_dir / "selected_checkpoints" / "checkpoint_manifest.json",
                "--output-dir",
                work_dir / "harness_repeated_judge",
                "--judge-repeats",
                str(harness_judge_repeats),
                "--concurrency",
                str(args.concurrency),
                "--judge-provider",
                args.judge_provider,
                "--judge-model",
                judge_model,
                "--judge-prompt-profile",
                resolved_harness_judge_prompt_profile(harness_profiles, args),
                "--codex-reasoning-effort",
                args.codex_reasoning_effort,
                "--max-attempts",
                str(args.judge_max_attempts),
            )
            if args.collect_only:
                command.append("--collect-only")
            step("harness_repeated_judge", command)

        if args.evaluate_trajectory and not args.skip_harness:
            trajectory_judge_repeats = max([resolved_judge_repeats(profile, args) for profile in harness_profiles] or [args.judge_repeats or 5])
            command = python_cmd(
                "scripts.evaluation.evaluate_snapshots",
                "--snapshot-manifest",
                work_dir / "snapshots" / "snapshot_manifest.json",
                "--output-dir",
                work_dir / "trajectory_repeated_judge",
                "--judge-repeats",
                str(trajectory_judge_repeats),
                "--concurrency",
                str(args.concurrency),
                "--judge-provider",
                args.judge_provider,
                "--judge-model",
                judge_model,
                "--judge-prompt-profile",
                resolved_harness_judge_prompt_profile(harness_profiles, args) if harness_profiles else (args.judge_prompt_profile or DEFAULT_DIRECTIONAL_JUDGE_PROMPT_PROFILE),
                "--codex-reasoning-effort",
                args.codex_reasoning_effort,
                "--max-attempts",
                str(args.judge_max_attempts),
            )
            if args.collect_only:
                command.append("--collect-only")
            step("trajectory_repeated_judge", command)

    if not args.skip_harness:
        step(
            "trajectory_summary",
            python_cmd(
                "scripts.evaluation.summarize_trajectory",
                "--protocol-dir",
                work_dir,
            ),
        )

    summary_command = python_cmd(
        "scripts.evaluation.summarize_results",
        "--protocol-dir",
        work_dir,
        "--out-dir",
        work_dir / "summaries",
        "--bootstrap-samples",
        str(args.bootstrap_samples),
        "--bootstrap-seed",
        str(args.bootstrap_seed),
    )
    if args.profile_config:
        summary_command.extend(["--profile-config", str(args.profile_config)])
    step(
        "summary",
        summary_command,
    )
    manifest["completed_at_utc"] = utc_now()
    manifest["status"] = "completed" if failures == 0 else "failed"
    write_json(manifest_path, manifest)
    print(f"Wrote protocol manifest to {manifest_path}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
