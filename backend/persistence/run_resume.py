from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.settings import RUN_RECORD_FILENAME
from backend.persistence.run_record_integrity import (
    RunRecordIntegrityError,
    read_canonical_run_record,
)
from backend.persistence.run_path_references import run_relative_reference
from backend.persistence.run_paths import safe_run_dir
from backend.persistence.run_resume_checkpoints import (
    RESUMABLE_ASYNC_OP_PATCH_STAGES,
    checkpoint_is_sane,
    latest_checkpoint_dir_resume_checkpoint,
    load_checkpoint_file,
)
from backend.persistence.run_resume_trace import latest_trace_resume_checkpoint
from harnesses.contracts import EffectiveHarnessRunSpec, HarnessExecutorId


_STRUCTURED_PATCH_EXECUTORS = frozenset(
    {
        HarnessExecutorId.STRUCTURED_PATCH_LEGACY,
        HarnessExecutorId.STRUCTURED_PATCH_REFINED,
    }
)


def latest_async_op_patch_resume_checkpoint(
    run_dir: Path,
    record: dict[str, Any] | None = None,
    *,
    max_trace_index: int | None = None,
) -> dict[str, Any] | None:
    if max_trace_index is None:
        checkpoint = latest_checkpoint_dir_resume_checkpoint(run_dir)
        if checkpoint is not None:
            return checkpoint
    return latest_trace_resume_checkpoint(run_dir, record, max_trace_index=max_trace_index)


def async_op_patch_resume_state(
    source_job_id: str,
    *,
    effective_harness_run_spec: EffectiveHarnessRunSpec,
    trace_index: int | None = None,
    runs_dir: Path,
) -> dict[str, Any]:
    source_run_dir = safe_run_dir(source_job_id, runs_dir=runs_dir)
    record_path = source_run_dir / RUN_RECORD_FILENAME
    if not record_path.is_file():
        raise HTTPException(status_code=404, detail="Source run not found.")
    try:
        source_record = read_canonical_run_record(record_path, runs_dir=runs_dir)
    except RunRecordIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="run_record_integrity_error",
        ) from exc
    if effective_harness_run_spec.executor_id not in _STRUCTURED_PATCH_EXECUTORS:
        raise HTTPException(status_code=400, detail="Selected run is not a Structured Patch Model run.")

    selected = latest_async_op_patch_resume_checkpoint(source_run_dir, source_record, max_trace_index=trace_index)
    if selected is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Selected Structured Patch run has no sane structured-model checkpoint to resume from"
                + (" at or before the selected trace row." if trace_index is not None else ".")
            ),
        )

    selected_payload = selected.get("payload") if isinstance(selected.get("payload"), dict) else {}
    structured_model = (
        selected_payload.get("structured_model") if isinstance(selected_payload.get("structured_model"), dict) else selected_payload
    )
    return {
        "runtime_harness_id": effective_harness_run_spec.harness_id,
        "source_job_id": source_job_id,
        "stage": selected["stage"],
        "checkpoint_path": run_relative_reference(
            source_run_dir,
            str(selected["path"]),
        ),
        "trace_index": trace_index,
        "payload": selected_payload,
        "structured_model": structured_model,
    }


def run_resume_state(
    source_job_id: str,
    *,
    effective_harness_run_spec: EffectiveHarnessRunSpec,
    trace_index: int | None = None,
    runs_dir: Path,
) -> dict[str, Any]:
    if effective_harness_run_spec.executor_id in _STRUCTURED_PATCH_EXECUTORS:
        return async_op_patch_resume_state(
            source_job_id,
            effective_harness_run_spec=effective_harness_run_spec,
            trace_index=trace_index,
            runs_dir=runs_dir,
        )
    raise HTTPException(
        status_code=400,
        detail="Resume is currently supported only for Structured Patch Model runs.",
    )


__all__ = [
    "RESUMABLE_ASYNC_OP_PATCH_STAGES",
    "async_op_patch_resume_state",
    "checkpoint_is_sane",
    "latest_async_op_patch_resume_checkpoint",
    "load_checkpoint_file",
    "run_resume_state",
]
