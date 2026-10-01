from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.models import CorrectionPatchRequest
from backend.api.settings import RUN_RECORD_FILENAME, RUN_TRACE_FILENAME
from backend.persistence.run_reconciliation import reconcile_inactive_running_run
from backend.persistence.run_paths import safe_run_dir
from backend.persistence.run_record_integrity import (
    RunRecordIntegrityError,
    read_canonical_run_record,
)
from backend.persistence.run_specifications import RunSpecificationIntegrityError
from backend.persistence.run_sources import source_run_specification, structured_model_from_run_dir
from core.schemas import StructuredModel
from backend.services.active_run_registry import ActiveRun, active_run_registry, run_is_active
from backend.services.correction_clients import correction_client_from_run_record
from backend.services.correction_events import CorrectionEventRecorder
from backend.services.recorded_patch_policy import (
    RecordedPatchPolicy,
    RecordedPatchPolicyError,
    recorded_patch_policy,
)
from backend.services.post_run_stream_control import PostRunStreamControl
from backend.services.trace_event_recorder import AsyncEventEmitter, AsyncEventSink


@dataclass(slots=True)
class FreeformCorrectionContext:
    run_dir: Path
    sessions_dir: Path
    record_path: Path
    record: dict[str, Any]
    model: StructuredModel
    specification: str
    trace_path: Path
    event_recorder: CorrectionEventRecorder
    emit: AsyncEventEmitter
    provider: str
    model_name: str
    base_url: str
    client: Any
    session_id: str | None
    message: str
    patch_policy: RecordedPatchPolicy


def load_freeform_correction_context(
    job_id: str,
    request: CorrectionPatchRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    event_sink: AsyncEventSink | None = None,
    stream_control: PostRunStreamControl | None = None,
    active_runs: dict[str, ActiveRun] | None = None,
    event_recorder: CorrectionEventRecorder | None = None,
) -> FreeformCorrectionContext:
    if run_is_active(job_id, active_runs):
        raise HTTPException(status_code=409, detail="Cannot apply correction patches while the run is still active.")
    # Resolve the trusted directory before reading the record so active-run
    # rejection never depends on persistence that the active worker may be
    # repairing or finalizing.
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
    record = reconcile_inactive_running_run(run_dir, record, active_run_ids=active_run_registry(active_runs))
    model = structured_model_from_run_dir(run_dir)
    if model is None:
        raise HTTPException(status_code=409, detail="Run has no valid structured model to patch.")
    try:
        specification = source_run_specification(run_dir, record)
    except RunSpecificationIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="run_specification_integrity_error",
        ) from exc

    trace_path = run_dir / RUN_TRACE_FILENAME
    if event_recorder is None:
        event_recorder = CorrectionEventRecorder(
            trace_path=trace_path,
            event_sink=event_sink,
            stream_control=stream_control,
        )
    elif event_recorder.trace_path != trace_path:
        raise ValueError("Shared correction recorder belongs to another run.")
    provider, model_name, base_url, client = correction_client_from_run_record(record)
    session_id = str(record.get("session_id") or "").strip() or None
    return FreeformCorrectionContext(
        run_dir=run_dir,
        sessions_dir=sessions_dir,
        record_path=record_path,
        record=record,
        model=model,
        specification=specification,
        trace_path=trace_path,
        event_recorder=event_recorder,
        emit=event_recorder.emit,
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        client=client,
        session_id=session_id,
        message=request.message.strip(),
        patch_policy=patch_policy,
    )
