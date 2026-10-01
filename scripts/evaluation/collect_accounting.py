from __future__ import annotations

import argparse
from pathlib import Path

from judge import write_generation_accounting


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect generation model-call and run accounting from generated artifacts.")
    parser.add_argument("--run", required=True, type=Path, help="Generation output directory to scan.")
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    reports = write_generation_accounting(args.run, args.out_dir)
    print(
        "Wrote accounting: "
        f"{len(reports['model_call_accounting'])} calls, "
        f"{len(reports['generation_run_summary'])} run summaries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
