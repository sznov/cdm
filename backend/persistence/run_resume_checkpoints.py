from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.persistence.common import read_json_file
from core.schemas import StructuredModel

RESUMABLE_ASYNC_OP_PATCH_STAGES = {
    "async-op-patch-after-draft": 10,
    "async-op-patch-after-language-repair": 20,
    "async-op-patch-after-coverage-critic": 30,
    "async-op-patch-after-patch-operations": 40,
    "structured-patch-base-complete": 40,
}


def load_checkpoint_file(path: Path) -> dict[str, Any] | None:
    try:
        checkpoint = read_json_file(path)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("payload"), dict):
        return None
    return checkpoint


def checkpoint_is_sane(stage: str, payload: dict[str, Any]) -> bool:
    if stage.startswith("structured-model-"):
        try:
            StructuredModel.model_validate(payload)
        except Exception:
            return False
        return True
    if stage.startswith("async-op-patch-") or stage == "structured-patch-base-complete":
        model_payload = payload.get("structured_model") if isinstance(payload.get("structured_model"), dict) else payload
        try:
            StructuredModel.model_validate(model_payload)
        except Exception:
            return False
        return True
    return False


def latest_checkpoint_dir_resume_checkpoint(run_dir: Path) -> dict[str, Any] | None:
    checkpoint_dir = run_dir / "checkpoints"
    if not checkpoint_dir.is_dir():
        return None

    candidates: list[dict[str, Any]] = []
    for path in checkpoint_dir.glob("*.json"):
        checkpoint = load_checkpoint_file(path)
        if checkpoint is None:
            continue
        stage = str(checkpoint.get("stage") or "")
        payload = checkpoint.get("payload") if isinstance(checkpoint.get("payload"), dict) else {}
        if stage not in RESUMABLE_ASYNC_OP_PATCH_STAGES or not checkpoint_is_sane(stage, payload):
            continue
        candidates.append({**checkpoint, "path": str(path), "order": RESUMABLE_ASYNC_OP_PATCH_STAGES[stage]})
    if not candidates:
        return None
    return max(candidates, key=lambda item: (int(item.get("order") or 0), str(item.get("timestamp_utc") or "")))


__all__ = [
    "RESUMABLE_ASYNC_OP_PATCH_STAGES",
    "checkpoint_is_sane",
    "latest_checkpoint_dir_resume_checkpoint",
    "load_checkpoint_file",
]
