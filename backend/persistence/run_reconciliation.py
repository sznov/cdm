from __future__ import annotations

from collections.abc import Container
from pathlib import Path
from typing import Any

from backend.api.settings import RUN_RECORD_FILENAME, RUN_TRACE_FILENAME
from backend.persistence.common import utc_now_iso
from backend.persistence.run_record_integrity import validate_canonical_run_record
from backend.persistence.run_path_references import (
    RUN_RELATIVE_PATH_REFERENCE_MODE,
    run_relative_reference,
)
from backend.persistence.run_records import mutate_persisted_run_record
from backend.persistence.run_trace import append_trace_event
from core.statuses import RUN_STATUS_FAILED, RUN_STATUS_INTERRUPTED, run_status_is_active


def model_call_log_error(text: str) -> str | None:
    marker = "\n=== ERROR ===\n"
    if marker not in text:
        return None
    error = text.split(marker, 1)[1].strip()
    return error or None


def latest_model_call_error(run_dir: Path) -> tuple[str, Path] | None:
    model_call_dir = run_dir / "model_calls"
    if not model_call_dir.is_dir():
        return None
    for log_path in sorted(model_call_dir.glob("*.txt"), key=lambda path: path.stat().st_mtime, reverse=True):
        try:
            error = model_call_log_error(log_path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if error:
            return error, log_path
    return None


def reconcile_inactive_running_run(
    run_dir: Path,
    record: dict[str, Any],
    *,
    active_run_ids: Container[str] | None = None,
) -> dict[str, Any]:
    record = validate_canonical_run_record(record)
    if not run_status_is_active(record.get("status")):
        return record
    job_id = str(record.get("job_id") or run_dir.name)
    if active_run_ids is not None and job_id in active_run_ids:
        return record

    reconciled_at = utc_now_iso()
    changes: dict[str, Any] = {}
    detail = ""

    def reconcile(latest_record: dict[str, Any]) -> None:
        nonlocal changes, detail
        if not run_status_is_active(latest_record.get("status")):
            return
        latest_error = latest_model_call_error(run_dir)
        if latest_error is not None:
            error, log_path = latest_error
            log_reference = (
                run_relative_reference(run_dir, log_path)
                if latest_record.get("path_reference_mode")
                == RUN_RELATIVE_PATH_REFERENCE_MODE
                else str(log_path)
            )
            changes = {
                "status": RUN_STATUS_FAILED,
                "completed_at_utc": latest_record.get("completed_at_utc") or reconciled_at,
                "error": error[:2000],
                "reconciled_at_utc": reconciled_at,
                "reconciled_from": "model_call_log_error",
                "reconciled_model_call_log": log_reference,
            }
            detail = f"Inactive running run reconciled as failed from model-call log {log_path.name}."
        else:
            changes = {
                "status": RUN_STATUS_INTERRUPTED,
                "completed_at_utc": latest_record.get("completed_at_utc") or reconciled_at,
                "error": "Run was marked active, but no active worker exists in this server process.",
                "reconciled_at_utc": reconciled_at,
                "reconciled_from": (
                    "inactive_stream_disconnect"
                    if latest_record.get("stream_disconnected_at_utc")
                    else "inactive_worker_missing"
                ),
            }
            detail = "Inactive running run reconciled as interrupted because no active worker exists."
        latest_record.update(changes)

    record = mutate_persisted_run_record(run_dir / RUN_RECORD_FILENAME, reconcile)
    if not changes:
        return record
    append_trace_event(
        run_dir / RUN_TRACE_FILENAME,
        event="run_reconciled",
        payload={"job_id": job_id, "status": record.get("status"), "detail": detail, **changes},
        timestamp_utc=reconciled_at,
    )
    return record
