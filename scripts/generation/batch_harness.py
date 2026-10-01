from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from core.runtime_env import load_dotenv_file
from harnesses.structured_patch.harness_runner import (
    DEFAULT_STRUCTURED_PATCH_HARNESS_ID,
    run_structured_patch_batch,
)


async def command_generate(args: argparse.Namespace) -> int:
    load_dotenv_file()
    code = await run_structured_patch_batch(
        spec_dir=args.spec_dir,
        out_dir=args.out_dir,
        reference_dir=args.reference_dir,
        spec_ids=args.spec_id,
        generation_repeats=args.generation_repeats,
        concurrency=args.concurrency,
        resume=args.resume,
        max_attempts=args.max_attempts,
        profile=args.profile,
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
        max_completion_tokens=args.max_completion_tokens,
        harness_id=args.harness_id,
        auto_correction_sequence=None if args.auto_correction_sequence is None else args.auto_correction_sequence,
        correction_template_id=args.correction_template_id,
    )
    print(f"Wrote harness rows to {args.out_dir / 'checkpoint_manifest.json'}")
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the structured-patch harness in batch mode without FastAPI.")
    parser.add_argument("--spec-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", type=Path)
    parser.add_argument("--spec-id", action="append", default=[])
    parser.add_argument("--generation-repeats", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Whole-harness attempts per specification; phase retries remain catalog-owned.",
    )
    parser.add_argument("--profile", default="harness-gemma")
    parser.add_argument("--harness-id", default=DEFAULT_STRUCTURED_PATCH_HARNESS_ID)
    parser.add_argument("--provider", choices=("gemini", "nvidia_nim"), default="gemini")
    parser.add_argument("--model", help="Defaults to the selected provider's default model.")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--max-completion-tokens", type=int)
    correction = parser.add_mutually_exclusive_group()
    correction.add_argument("--auto-correction-sequence", dest="auto_correction_sequence", action="store_true")
    correction.add_argument("--no-auto-correction-sequence", dest="auto_correction_sequence", action="store_false")
    parser.add_argument("--correction-template-id")
    parser.set_defaults(auto_correction_sequence=None)
    return parser


def main() -> int:
    return asyncio.run(command_generate(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
