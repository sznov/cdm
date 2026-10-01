from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from core.runtime_env import load_dotenv_file
from harnesses.direct_baseline.runner import run_direct_baseline_generation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate direct baseline/reference artifacts.")
    parser.add_argument("--spec-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", type=Path)
    parser.add_argument("--spec-id", action="append", default=[])
    parser.add_argument("--generation-repeats", type=int, default=1)
    parser.add_argument("--target-valid-generations", type=int, default=None)
    parser.add_argument("--fill-max-attempts", type=int, default=None)
    parser.add_argument("--profile", default="gemma-baseline")
    parser.add_argument(
        "--prompt-profile",
        default="schema_only_v1",
        choices=("schema_only_v1", "structured_draft_with_issues"),
        help="Prompt contract for direct generation. Defaults to the legacy schema-only baseline.",
    )
    parser.add_argument("--provider", choices=("gemini", "codex", "nvidia_nim"), default="gemini")
    parser.add_argument("--model", help="Defaults to the selected provider's default model.")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--max-completion-tokens", type=int, default=32768)
    parser.add_argument("--codex-reasoning-effort", default="xhigh")
    return parser


async def command_generate(args: argparse.Namespace) -> int:
    load_dotenv_file()
    try:
        result = await run_direct_baseline_generation(
            spec_dir=args.spec_dir,
            out_dir=args.out_dir,
            reference_dir=args.reference_dir,
            spec_ids=args.spec_id,
            generation_repeats=args.generation_repeats,
            target_valid_generations=args.target_valid_generations,
            fill_max_attempts=args.fill_max_attempts,
            profile=args.profile,
            prompt_profile_id=args.prompt_profile,
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            timeout_seconds=args.timeout_seconds,
            max_completion_tokens=args.max_completion_tokens,
            codex_reasoning_effort=args.codex_reasoning_effort,
            created_by="python -m scripts.generation.direct_baseline",
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote checkpoint rows to {args.out_dir / 'checkpoint_manifest.json'}")
    return result


def main() -> int:
    return asyncio.run(command_generate(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
