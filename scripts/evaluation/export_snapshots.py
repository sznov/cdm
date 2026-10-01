from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from core.artifacts import load_json, write_csv, write_json
from core.plantuml_structured import render_structured_model_to_plantuml
from core.schemas import StructuredModel
from harnesses.structured_patch.trajectory import enrich_structured_patch_snapshot_rows


SNAPSHOT_FIELDS = [
    "spec_id",
    "generation_run_id",
    "snapshot_id",
    "snapshot_index",
    "checkpoint_label",
    "source_stage",
    "summary",
    "status",
    "spec_path",
    "reference_model_path",
    "gold_path",
    "model_path",
    "plantuml_path",
    "source_checkpoint_path",
    "source_result_path",
    "run_started_at_utc",
    "checkpoint_timestamp_utc",
    "cumulative_seconds",
    "cumulative_minutes",
    "previous_snapshot_id",
    "parent_snapshot_id",
    "is_correction_step",
    "correction_step_index",
]


def slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return text or "snapshot"


def reference_path_for(reference_dir: Path | None, spec_id: str) -> str:
    if reference_dir is None:
        return ""
    for candidate in (
        reference_dir / spec_id / "structured_model.json",
        reference_dir / f"{spec_id}.json",
        reference_dir / f"{spec_id}.structured_model.json",
    ):
        if candidate.exists():
            return str(candidate)
    return ""


def spec_path_for(spec_dir: Path | None, spec_id: str) -> str:
    if spec_dir is None:
        return ""
    path = spec_dir / f"{spec_id}.txt"
    return str(path) if path.exists() else ""


def generation_and_spec_from_job_dir(job_dir: Path, run_root: Path) -> tuple[str, str]:
    try:
        rel = job_dir.relative_to(run_root)
        parts = rel.parts
    except ValueError:
        parts = job_dir.parts
    if len(parts) >= 3 and parts[-3] == "harness_runs":
        return parts[-2], str(parts[-1]).zfill(3)
    if len(parts) >= 2:
        return parts[-2], str(parts[-1]).zfill(3)
    return "gen-001", str(job_dir.name).zfill(3)


def structured_payload_from_checkpoint(path: Path) -> tuple[str, dict[str, Any]] | None:
    record = load_json(path)
    if not isinstance(record, dict):
        return None
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    structured = payload.get("structured_model") if isinstance(payload, dict) else None
    if not isinstance(structured, dict):
        return None
    return str(record.get("stage") or path.stem), structured


def structured_payload_from_result(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    record = load_json(path)
    if not isinstance(record, dict):
        return None
    structured = record.get("structured_model")
    return structured if isinstance(structured, dict) else None


def write_snapshot_model(
    *,
    out_dir: Path,
    generation_id: str,
    spec_id: str,
    snapshot_id: str,
    structured_payload: dict[str, Any],
) -> tuple[str, str]:
    model = StructuredModel.model_validate(structured_payload)
    snapshot_dir = out_dir / "snapshots" / generation_id / spec_id
    model_path = snapshot_dir / f"{snapshot_id}.structured_model.json"
    plantuml_path = snapshot_dir / f"{snapshot_id}.plantuml"
    write_json(model_path, model.model_dump(mode="json"))
    plantuml_path.write_text(render_structured_model_to_plantuml(model), encoding="utf-8")
    return str(model_path), str(plantuml_path)


def collect_job_snapshots(
    *,
    job_dir: Path,
    run_root: Path,
    out_dir: Path,
    spec_dir: Path | None,
    reference_dir: Path | None,
) -> list[dict[str, Any]]:
    generation_id, spec_id = generation_and_spec_from_job_dir(job_dir, run_root)
    spec_path = spec_path_for(spec_dir, spec_id)
    reference_path = reference_path_for(reference_dir, spec_id)
    candidates: list[tuple[str, str, Path | None, Path | None, dict[str, Any]]] = []
    for checkpoint_path in sorted((job_dir / "checkpoints").glob("*.json")):
        parsed = structured_payload_from_checkpoint(checkpoint_path)
        if parsed is None:
            continue
        stage, payload = parsed
        candidates.append((stage, stage.replace("async-op-patch-", "").replace("-", " "), checkpoint_path, None, payload))
    final_payload = structured_payload_from_result(job_dir / "result.json")
    if final_payload is not None:
        candidates.append(("final", "Final model", None, job_dir / "result.json", final_payload))

    rows: list[dict[str, Any]] = []
    for index, (stage, summary, checkpoint_path, result_path, payload) in enumerate(candidates, start=1):
        snapshot_id = f"{index:03d}_{slug(stage)}"
        model_path, plantuml_path = write_snapshot_model(
            out_dir=out_dir,
            generation_id=generation_id,
            spec_id=spec_id,
            snapshot_id=snapshot_id,
            structured_payload=payload,
        )
        rows.append(
            {
                "spec_id": spec_id,
                "generation_run_id": generation_id,
                "snapshot_id": snapshot_id,
                "snapshot_index": index,
                "checkpoint_label": stage,
                "source_stage": stage,
                "summary": summary,
                "status": "pending",
                "spec_path": spec_path,
                "reference_model_path": reference_path,
                "gold_path": reference_path,
                "model_path": model_path,
                "plantuml_path": plantuml_path,
                "source_checkpoint_path": str(checkpoint_path) if checkpoint_path is not None else "",
                "source_result_path": str(result_path) if result_path is not None else "",
            }
        )
    return rows


def export_snapshots(run_root: Path, out_dir: Path, spec_dir: Path | None, reference_dir: Path | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    job_dirs = sorted({path.parent for path in run_root.rglob("result.json")} | {path.parent.parent for path in run_root.rglob("checkpoints/*.json")})
    for job_dir in job_dirs:
        rows.extend(
            collect_job_snapshots(
                job_dir=job_dir,
                run_root=run_root,
                out_dir=out_dir,
                spec_dir=spec_dir,
                reference_dir=reference_dir,
            )
        )
    rows = enrich_structured_patch_snapshot_rows(rows, run_root)
    rows.sort(key=lambda row: (str(row["spec_id"]), str(row["generation_run_id"]), int(row["snapshot_index"])))
    write_json(out_dir / "snapshot_manifest.json", rows)
    write_csv(out_dir / "snapshot_manifest.csv", rows, SNAPSHOT_FIELDS)
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export first/revised/final/intermediate model snapshots from harness artifacts.")
    parser.add_argument("--run", required=True, type=Path, help="Generation output directory to scan.")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--spec-dir", type=Path)
    parser.add_argument("--reference-dir", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = export_snapshots(args.run, args.out_dir, args.spec_dir, args.reference_dir)
    print(f"Wrote {len(rows)} snapshots to {args.out_dir / 'snapshot_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
