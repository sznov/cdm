from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.models import QuestionRequest
from backend.api.settings import RUN_TRACE_FILENAME
from backend.persistence.common import read_json_file
from backend.persistence.run_reconciliation import reconcile_inactive_running_run
from backend.persistence.run_specifications import RunSpecificationIntegrityError
from backend.persistence.run_sources import source_run_specification, structured_model_from_run_dir
from core.schemas import StructuredModel
from backend.services.active_run_registry import ActiveRun, active_run_registry, run_is_active
from backend.services.correction_clients import correction_client_from_run_record
from backend.services.decision_patches import decision_patches_for_run
from backend.services.recorded_patch_policy import RecordedPatchPolicyError, recorded_patch_policy
from backend.services.post_run_stream_control import PostRunStreamControl
from backend.services.run_queries import read_run_record
from backend.services.trace_event_recorder import (
    AsyncEventEmitter,
    AsyncEventSink,
    TraceEventRecorder,
)


@dataclass(slots=True)
class ModelQuestionContext:
    run_dir: Path
    sessions_dir: Path
    record: dict[str, Any]
    specification: str
    structured_model: StructuredModel | None
    working_model_payload: dict[str, Any] | None
    question: str
    provider: str
    model_name: str
    base_url: str
    client: Any
    session_id: str | None
    decision_patches: list[dict[str, Any]]
    event_recorder: TraceEventRecorder
    emit: AsyncEventEmitter


def load_model_question_context(
    job_id: str,
    request: QuestionRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    event_sink: AsyncEventSink | None = None,
    stream_control: PostRunStreamControl | None = None,
    active_runs: dict[str, ActiveRun] | None = None,
) -> ModelQuestionContext:
    run_dir, record = read_run_record(job_id, runs_dir=runs_dir)
    if run_is_active(job_id, active_runs):
        raise HTTPException(status_code=409, detail="Cannot ask about a run while it is still active.")
    record = reconcile_inactive_running_run(run_dir, record, active_run_ids=active_run_registry(active_runs))
    try:
        patch_policy = recorded_patch_policy(record)
    except RecordedPatchPolicyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        specification = source_run_specification(run_dir, record)
    except RunSpecificationIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="run_specification_integrity_error",
        ) from exc

    structured_model = structured_model_from_run_dir(run_dir)
    working_model_payload = None
    working_model_path = run_dir / "working_model.json"
    if working_model_path.is_file():
        try:
            working_model_payload = read_json_file(working_model_path)
        except (OSError, json.JSONDecodeError):
            working_model_payload = None
    if structured_model is None and working_model_payload is None:
        raise HTTPException(status_code=409, detail="Run has no model artifact to ask about.")

    provider, model_name, base_url, client = correction_client_from_run_record(record)
    session_id = str(record.get("session_id") or "").strip() or None
    event_recorder = TraceEventRecorder(
        trace_path=run_dir / RUN_TRACE_FILENAME,
        event_sink=event_sink,
        stream_control=stream_control,
    )
    return ModelQuestionContext(
        run_dir=run_dir,
        sessions_dir=sessions_dir,
        record=record,
        specification=specification,
        structured_model=structured_model,
        working_model_payload=working_model_payload,
        question=request.question.strip(),
        provider=provider,
        model_name=model_name,
        base_url=base_url,
        client=client,
        session_id=session_id,
        decision_patches=decision_patches_for_run(
            run_dir,
            record,
            name_policy=patch_policy.name_policy,
        ),
        event_recorder=event_recorder,
        emit=event_recorder.emit,
    )


__all__ = ["ModelQuestionContext", "load_model_question_context"]
