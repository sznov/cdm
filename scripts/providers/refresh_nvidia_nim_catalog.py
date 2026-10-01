from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from core.providers.nvidia_nim_discovery import (
    discover_nvidia_nim_v1_model_ids,
    fetch_nvidia_nim_build_entries,
    merge_nvidia_nim_build_entries,
    read_nvidia_nim_catalog_cache,
    write_nvidia_nim_catalog_cache,
)
from core.providers.nvidia_nim_catalog import (
    merge_v1_model_ids,
)
from core.runtime_env import load_dotenv_file


DEFAULT_CACHE_PATH = Path("__db__") / "providers" / "nvidia_nim_catalog.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh the cached NVIDIA NIM model catalog.")
    parser.add_argument("--base-url", help="NVIDIA NIM base URL. Defaults to NVIDIA_NIM_BASE_URL or hosted Build.")
    parser.add_argument("--cache-path", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--skip-v1-models", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    return parser


async def command_refresh(args: argparse.Namespace) -> int:
    load_dotenv_file()
    entries = read_nvidia_nim_catalog_cache(args.cache_path)
    if not args.skip_build:
        try:
            entries = merge_nvidia_nim_build_entries(entries, await fetch_nvidia_nim_build_entries())
        except Exception as exc:
            print(f"Build catalog enrichment failed; keeping existing metadata. {exc}")
    if not args.skip_v1_models:
        model_ids = await discover_nvidia_nim_v1_model_ids(base_url=args.base_url)
        entries = merge_v1_model_ids(entries, model_ids)
    write_nvidia_nim_catalog_cache(entries, args.cache_path)
    print(f"Wrote {len(entries)} NVIDIA NIM catalog entries to {args.cache_path}")
    return 0


def main() -> int:
    return asyncio.run(command_refresh(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
