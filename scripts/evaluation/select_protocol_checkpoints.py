from __future__ import annotations

import argparse
from pathlib import Path

from core.artifacts import load_json, write_checkpoint_manifest, write_csv, write_json
from judge import select_protocol_checkpoints


CHECKPOINT_FIELDS = [
    "spec_id",
    "generation_run_id",
    "checkpoint_label",
    "source_snapshot_id",
    "source_snapshot_index",
    "carried_forward",
    "summary",
    "model_path",
    "gold_path",
    "spec_path",
    "eval_dir",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select first/revised/final protocol checkpoints from a snapshot manifest.")
    parser.add_argument("--snapshot-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="JSON output path for selected protocol checkpoints.")
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--generation-run-id", help="Optional single generation id to select; omitted selects all generations.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = load_json(args.snapshot_manifest)
    if not isinstance(rows, list):
        raise SystemExit(f"Snapshot manifest must be a list: {args.snapshot_manifest}")
    selected = select_protocol_checkpoints([row for row in rows if isinstance(row, dict)], args.generation_run_id)
    write_json(args.output, selected)
    if args.output.name == "checkpoint_manifest.json":
        write_checkpoint_manifest(args.output.parent, selected)
    if args.csv_output:
        write_csv(args.csv_output, selected, CHECKPOINT_FIELDS)
    print(f"Wrote {len(selected)} protocol checkpoint rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
