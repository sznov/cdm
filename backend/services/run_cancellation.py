from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.settings import RUN_RECORD_FILENAME, RUN_TRACE_FILENAME
from backend.persistence.common import utc_now_iso
from backend.persistence.locks import run_lock
from backend.persistence.run_records import mutate_persisted_run_record
from backend.persistence.run_trace import append_trace_event
from backend.services.active_run_registry import ActiveRun
from backend.services.run_queries import read_run_record
from core.statuses import RUN_STATUS_CANCELLING, run_status_is_terminal


def cancel_run(
    job_id: str,
    *,
    runs_dir: Path,
    active_runs: Mapping[str, ActiveRun],
) -> dict[str, Any]:
    run_dir, record = read_run_record(job_id, runs_dir=runs_dir)
    record_path = run_dir / RUN_RECORD_FILENAME

    active = active_runs.get(job_id)
    status = str(record.get("status") or "unknown")
    if active is None and not run_status_is_terminal(status):
        raise HTTPException(status_code=409, detail="Run is not active in this server process.")

    requested_at = utc_now_iso()
    cancellation_requested = False

    def request_cancellation(latest: dict[str, Any]) -> None:
        nonlocal cancellation_requested
        if run_status_is_terminal(str(latest.get("status") or "unknown")):
            return
        latest.update(
            status=RUN_STATUS_CANCELLING,
            cancel_requested_at_utc=requested_at,
            error="Cancellation requested by user.",
        )
        cancellation_requested = True

    with run_lock(run_dir):
        record = mutate_persisted_run_record(record_path, request_cancellation)
        if cancellation_requested:
            payload = {
                "job_id": job_id,
                "requested_at_utc": requested_at,
                "detail": "Cancellation requested by user.",
            }
            append_trace_event(
                run_dir / RUN_TRACE_FILENAME,
                event="cancel_requested",
                payload=payload,
                timestamp_utc=requested_at,
            )
    if not cancellation_requested:
        return {"job_id": job_id, "status": str(record.get("status") or "unknown"), "cancelled": False}

    assert active is not None
    active.task.cancel()
    return {"job_id": job_id, "status": RUN_STATUS_CANCELLING, "cancelled": True}


__all__ = ["cancel_run"]
