from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from core.runtime_env import load_dotenv_file
from harnesses.structured_patch.harness_runner import run_structured_patch_batch


async def command_generate(args: argparse.Namespace) -> int:
    load_dotenv_file()
    code = await run_structured_patch_batch(
        spec_dir=args.spec_dir,
        out_dir=args.out_dir,
        reference_dir=None,
        spec_ids=args.spec_id,
        generation_repeats=args.generation_repeats,
        concurrency=1,
        resume=False,
        max_attempts=args.max_attempts,
        profile="harness-gemma",
        provider="gemini",
        model=args.model,
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
    )
    print(f"Wrote harness rows to {args.out_dir / 'checkpoint_manifest.json'}")
    return code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate structured-patch harness artifacts without FastAPI.")
    parser.add_argument("--spec-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--spec-id", action="append", default=[])
    parser.add_argument("--generation-repeats", type=int, default=1)
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Whole-harness attempts per specification; phase retries remain catalog-owned.",
    )
    parser.add_argument("--model", default="gemma-4-31b-it")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    return parser


def main() -> int:
    return asyncio.run(command_generate(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
