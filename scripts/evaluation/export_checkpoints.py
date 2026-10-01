from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from core.artifacts import load_json, write_checkpoint_manifest


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _result_checkpoint(job_dir: Path, root: Path) -> dict[str, Any] | None:
    result_path = job_dir / "result.json"
    if not result_path.exists():
        return None
    result = load_json(result_path)
    if not isinstance(result, dict):
        return None
    return {
        "spec_id": result.get("spec_id", job_dir.name),
        "generation_run_id": result.get("generation_run_id", job_dir.parent.name),
        "checkpoint_label": result.get("checkpoint_label", "final"),
        "model_path": _relative_to_root(result_path, root),
        "plantuml_path": _relative_to_root(job_dir / "final.plantuml", root),
        "provider": result.get("provider", ""),
        "model": result.get("model", ""),
    }


def collect_result_checkpoints(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result_path in sorted(root.rglob("result.json")):
        row = _result_checkpoint(result_path.parent, root)
        if row is not None:
            rows.append(row)
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a checkpoint_manifest.json from generated result directories.")
    parser.add_argument("--run", required=True, type=Path, help="Generation run directory to scan.")
    parser.add_argument("--out", type=Path, help="Directory that receives checkpoint_manifest.json. Defaults to --run.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    out_dir = args.out or args.run
    rows = collect_result_checkpoints(args.run)
    write_checkpoint_manifest(out_dir, rows)
    print(f"Wrote {len(rows)} checkpoint rows to {out_dir / 'checkpoint_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
