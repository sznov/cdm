from __future__ import annotations

from datetime import datetime, timezone
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from core.atomic_io import atomic_write_text
from harnesses.contracts import CheckpointArtifact, CheckpointReference


def write_one_shot_run_checkpoint(
    model_call_log_dir: Path | None,
    *,
    job_id: str,
    stage: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    if model_call_log_dir is None:
        return None
    checkpoint_dir = model_call_log_dir.parent / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    path = checkpoint_dir / f"{stage}.json"
    timestamp_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    artifact = CheckpointArtifact.model_validate(
        {
            "job_id": job_id,
            "stage": stage,
            "timestamp_utc": timestamp_utc,
            "payload": deepcopy(payload),
        }
    )
    atomic_write_text(
        path,
        json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return CheckpointReference(
        job_id=job_id,
        stage=stage,
        path=str(path),
        timestamp_utc=timestamp_utc,
    ).model_dump(mode="json")


__all__ = ["write_one_shot_run_checkpoint"]
