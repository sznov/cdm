from __future__ import annotations

import argparse
import time
from pathlib import Path

from core.artifacts import append_timing, utc_now
from judge import aggregate_judged_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate judged conceptual-model evaluation artifacts.")
    parser.add_argument("--run", required=True, type=Path, help="Run directory containing profile_manifest.json and repeated_judge outputs.")
    parser.add_argument("--out", required=True, type=Path, help="Output directory for profile_summary and canonical manifest files.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    started_at = utc_now()
    monotonic_start = time.monotonic()
    status = "failed"
    returncode = 1
    try:
        rows = aggregate_judged_run(args.run, args.out)
        print(f"Wrote {len(rows)} summary rows to {args.out}")
        status = "completed"
        returncode = 0
        return 0
    finally:
        append_timing(
            args.out,
            {
                "phase": "aggregate",
                "step": "aggregate",
                "key": "all",
                "status": status,
                "started_at_utc": started_at,
                "duration_seconds": round(time.monotonic() - monotonic_start, 3),
                "command": "python -m scripts.evaluation.aggregate_judged_run",
                "returncode": returncode,
            },
        )


if __name__ == "__main__":
    raise SystemExit(main())
