from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.settings import RUN_RECORD_FILENAME, RUN_TRACE_FILENAME
from backend.persistence.common import utc_now_iso
from backend.persistence.run_paths import safe_run_dir
from backend.persistence.run_record_integrity import (
    RunRecordIntegrityError,
    read_canonical_run_record,
)
from backend.persistence.run_sources import structured_model_from_run_dir
from backend.persistence.run_trace import append_trace_event
from core.schemas import StructuredModel
from harnesses.structured_patch.name_policy import StructuredNamePolicy
from backend.services.active_run_registry import ActiveRun, run_is_active
from backend.services.decision_patches import (
    decision_patches_for_run,
    reject_conflicting_identifier_decision_choices,
    structured_language_rename_maps_for_run,
)
from backend.services.recorded_patch_policy import (
    RecordedPatchPolicy,
    RecordedPatchPolicyError,
    recorded_patch_policy,
)


@dataclass(slots=True)
class DecisionPatchApplicationContext:
    job_id: str
    run_dir: Path
    sessions_dir: Path
    record_path: Path
    record: dict[str, Any]
    model: StructuredModel
    patch_policy: RecordedPatchPolicy
    decision_rename_maps: dict[str, dict[str, str]]
    patches: list[dict[str, Any]]
    patch_by_id: dict[str, dict[str, Any]]
    trace_path: Path
    event_sequences: list[int] = field(default_factory=list)


def load_decision_patch_application_context(
    job_id: str,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    active_runs: dict[str, ActiveRun] | None = None,
) -> DecisionPatchApplicationContext:
    if run_is_active(job_id, active_runs):
        raise HTTPException(status_code=409, detail="Cannot apply decision patches while the run is still active.")
    run_dir = safe_run_dir(job_id, runs_dir=runs_dir)
    record_path = run_dir / RUN_RECORD_FILENAME
    try:
        record = read_canonical_run_record(record_path, runs_dir=runs_dir)
    except RunRecordIntegrityError as exc:
        raise HTTPException(status_code=409, detail="run_record_integrity_error") from exc
    try:
        patch_policy = recorded_patch_policy(record)
    except RecordedPatchPolicyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    model = structured_model_from_run_dir(run_dir)
    if model is None:
        raise HTTPException(status_code=409, detail="Run has no valid structured model to patch.")
    decision_rename_maps = structured_language_rename_maps_for_run(run_dir)
    patches = decision_patches_for_run(
        run_dir,
        record,
        name_policy=patch_policy.name_policy,
    )
    patch_by_id = {str(patch.get("id") or ""): patch for patch in patches if isinstance(patch, dict)}
    return DecisionPatchApplicationContext(
        job_id=job_id,
        run_dir=run_dir,
        sessions_dir=sessions_dir,
        record_path=record_path,
        record=record,
        model=model,
        patch_policy=patch_policy,
        decision_rename_maps=decision_rename_maps,
        patches=patches,
        patch_by_id=patch_by_id,
        trace_path=run_dir / RUN_TRACE_FILENAME,
    )


def validate_decision_choices(
    choices: list[dict[str, Any]],
    patch_by_id: dict[str, dict[str, Any]],
    *,
    name_policy: StructuredNamePolicy,
) -> list[str]:
    if not choices:
        raise HTTPException(status_code=400, detail="Select at least one decision.")
    requested_ids = [choice["patch_id"] for choice in choices]
    missing = [patch_id for patch_id in requested_ids if patch_id not in patch_by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Decision patch not found: {', '.join(missing)}")
    reject_conflicting_identifier_decision_choices(
        choices,
        patch_by_id,
        name_policy=name_policy,
    )
    return requested_ids


def emit_decision_patch_batch_start(
    context: DecisionPatchApplicationContext,
    *,
    requested_ids: list[str],
    choices: list[dict[str, Any]],
) -> None:
    record = append_trace_event(
        context.trace_path,
        event="decision_patch_batch_start",
        payload={
            "job_id": context.job_id,
            "patch_ids": requested_ids,
            "choices": choices,
            "summary": f"Applying {len(choices)} decision(s).",
        },
        timestamp_utc=utc_now_iso(),
    )
    context.event_sequences.append(int(record["sequence"]))
