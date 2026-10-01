from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.artifacts.models import CheckpointManifestRow


PROFILE_MANIFEST_FILENAME = "profile_manifest.json"
CHECKPOINT_MANIFEST_FILENAME = "checkpoint_manifest.json"
RUN_TIMING_FILENAME = "run_timing.json"
RUN_TIMING_CSV_FILENAME = "run_timing.csv"
CANONICAL_RUN_MANIFEST_FILENAME = "canonical_run_manifest.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_profile_manifest(output_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    manifest = {
        "created_at_utc": utc_now(),
        **payload,
    }
    write_json(output_dir / PROFILE_MANIFEST_FILENAME, manifest)
    return manifest


def write_checkpoint_manifest(output_dir: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = normalize_checkpoint_manifest_rows(rows)
    write_json(output_dir / CHECKPOINT_MANIFEST_FILENAME, normalized)
    return normalized


def read_checkpoint_manifest(run_dir: Path) -> list[dict[str, Any]]:
    return read_checkpoint_manifest_path(run_dir / CHECKPOINT_MANIFEST_FILENAME)


def read_checkpoint_manifest_path(path: Path) -> list[dict[str, Any]]:
    """Read and validate a checkpoint manifest at an explicit path."""

    payload = load_json(path)
    return normalize_checkpoint_manifest_rows(payload, source=path)


def normalize_checkpoint_manifest_rows(
    payload: Any,
    *,
    source: Path | None = None,
) -> list[dict[str, Any]]:
    """Validate an in-memory checkpoint manifest without dropping malformed rows."""

    if not isinstance(payload, list):
        label = str(source) if source is not None else CHECKPOINT_MANIFEST_FILENAME
        raise ValueError(f"Checkpoint manifest must contain a JSON list: {label}")
    return [CheckpointManifestRow.model_validate(row).detached_dict() for row in payload]


def write_canonical_run_manifest(output_dir: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    write_json(output_dir / CANONICAL_RUN_MANIFEST_FILENAME, rows)
    return rows


def timing_path(run_dir: Path) -> Path:
    return run_dir / RUN_TIMING_FILENAME


def _append_json_list(path: Path, row: dict[str, Any]) -> None:
    payload = load_json(path) if path.exists() else []
    if not isinstance(payload, list):
        payload = []
    payload.append(row)
    write_json(path, payload)


def append_timing(run_dir: Path, row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    normalized.setdefault("ended_at_utc", utc_now())
    _append_json_list(timing_path(run_dir), normalized)
    write_timing_csv(run_dir)
    return normalized


def completed_step(run_dir: Path, phase: str, step: str, key: str | None = None) -> bool:
    path = timing_path(run_dir)
    if not path.exists():
        return False
    payload = load_json(path)
    if not isinstance(payload, list):
        return False
    for row in payload:
        if not isinstance(row, dict):
            continue
        if row.get("phase") != phase or row.get("step") != step or row.get("status") != "completed":
            continue
        if key is None or row.get("key") == key:
            return True
    return False


def write_timing_csv(run_dir: Path) -> None:
    path = timing_path(run_dir)
    if not path.exists():
        return
    rows = load_json(path)
    if not isinstance(rows, list):
        return
    fields = [
        "phase",
        "step",
        "key",
        "status",
        "started_at_utc",
        "ended_at_utc",
        "duration_seconds",
        "command",
        "returncode",
    ]
    write_csv(run_dir / RUN_TIMING_CSV_FILENAME, rows, fields)
