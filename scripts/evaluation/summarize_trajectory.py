from __future__ import annotations

import argparse
from pathlib import Path

from core.artifacts import load_json
from judge.trajectory import build_trajectory_reports, load_optional_rows, write_trajectory_reports


def _load_rows(path: Path) -> list[dict]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise SystemExit(f"Expected JSON list: {path}")
    return [row for row in payload if isinstance(row, dict)]


def resolve_paths(args: argparse.Namespace) -> tuple[Path, Path | None, Path]:
    snapshot_manifest = args.snapshot_manifest
    majority_scores = args.majority_scores
    out_dir = args.out_dir
    if args.protocol_dir:
        protocol_dir = args.protocol_dir
        snapshot_manifest = snapshot_manifest or protocol_dir / "snapshots" / "snapshot_manifest.json"
        candidate_scores = protocol_dir / "trajectory_repeated_judge" / "majority_scores.json"
        if majority_scores is None and candidate_scores.exists():
            majority_scores = candidate_scores
        out_dir = out_dir or protocol_dir / "trajectory"
    if snapshot_manifest is None:
        raise SystemExit("--snapshot-manifest is required unless --protocol-dir is provided.")
    if out_dir is None:
        raise SystemExit("--out-dir is required unless --protocol-dir is provided.")
    return snapshot_manifest, majority_scores, out_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize snapshot trajectory timing, oracle-best checkpoints, and correction progression.")
    parser.add_argument("--protocol-dir", type=Path)
    parser.add_argument("--snapshot-manifest", type=Path)
    parser.add_argument("--majority-scores", type=Path)
    parser.add_argument("--run-timing", type=Path, help="Accepted for compatibility; snapshot manifests already carry timing fields.")
    parser.add_argument("--out-dir", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    snapshot_manifest, majority_scores_path, out_dir = resolve_paths(args)
    snapshot_rows = _load_rows(snapshot_manifest)
    majority_rows = load_optional_rows(majority_scores_path)
    reports = build_trajectory_reports(snapshot_rows, majority_rows)
    write_trajectory_reports(out_dir, reports)
    print(f"Wrote trajectory reports to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
