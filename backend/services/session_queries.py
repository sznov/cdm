from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.api.settings import RUN_RECORD_FILENAME, RUN_TRACE_FILENAME, SESSION_RECORD_FILENAME
from backend.persistence.run_records import summarize_run_record
from backend.persistence.post_run_transaction_guard import (
    PostRunTransactionPendingError,
    pending_post_run_transaction_id,
)
from backend.persistence.post_run_transactions import (
    committed_post_run_transaction_id,
    transaction_tagged_message_is_committed,
)
from backend.persistence.run_record_integrity import (
    RunRecordIntegrityError,
    read_canonical_run_record,
)
from backend.persistence.run_trace import TraceFormatError, trace_event_count
from backend.persistence.session_records import read_session_record
from backend.persistence.session_record_integrity import (
    SessionRecordIntegrityError,
    read_canonical_session_record,
    validate_canonical_session_record,
)
from core.statuses import run_status_is_active


RunRecordEntry = tuple[Path, dict[str, Any]]


def _run_order_key(entry: RunRecordEntry) -> tuple[str, str]:
    record = entry[1]
    timestamp = str(
        record.get("queued_at_utc")
        or record.get("started_at_utc")
        or record.get("completed_at_utc")
        or ""
    )
    return timestamp, str(record.get("job_id") or entry[0].name)


def session_run_records_by_session(runs_dir: Path) -> dict[str, list[RunRecordEntry]]:
    indexed: dict[str, list[RunRecordEntry]] = {}
    if not runs_dir.is_dir():
        return indexed
    for run_dir in runs_dir.iterdir():
        record_path = run_dir / RUN_RECORD_FILENAME
        if not run_dir.is_dir() or not record_path.is_file():
            continue
        try:
            if pending_post_run_transaction_id(run_dir) is not None:
                continue
            record = read_canonical_run_record(record_path, runs_dir=runs_dir)
        except (PostRunTransactionPendingError, RunRecordIntegrityError):
            continue
        session_id = str(record.get("session_id") or "").strip()
        if session_id:
            indexed.setdefault(session_id, []).append((run_dir, record))
    for entries in indexed.values():
        entries.sort(key=_run_order_key)
    return indexed


def session_payload_from_runs(
    record: dict[str, Any],
    run_entries: list[RunRecordEntry],
) -> dict[str, Any]:
    payload = validate_canonical_session_record(record)
    payload.pop("status", None)
    payload.pop("active_job_id", None)
    job_ids = [str(run.get("job_id") or run_dir.name) for run_dir, run in run_entries]
    active_entry = next(
        (entry for entry in reversed(run_entries) if run_status_is_active(entry[1].get("status"))),
        None,
    )
    latest = run_entries[-1][1] if run_entries else None
    committed_by_run = {
        run_dir.name: transaction_id
        for run_dir, _run_record in run_entries
        if (
            transaction_id := committed_post_run_transaction_id(run_dir)
        )
    }
    messages = (
        payload.get("chat_messages")
        if isinstance(payload.get("chat_messages"), list)
        else []
    )
    payload["chat_messages"] = [
        message
        for message in messages
        if not isinstance(message, dict)
        or transaction_tagged_message_is_committed(
            message,
            committed_by_run=committed_by_run,
        )
    ]
    payload.update(
        job_ids=job_ids,
        active_job_id=(str(active_entry[1].get("job_id") or active_entry[0].name) if active_entry else None),
        status=("running" if active_entry else str(latest.get("status") or "created") if latest else "created"),
    )
    return payload


def summarize_session_payload(record: dict[str, Any]) -> dict[str, Any]:
    job_ids = [str(job_id) for job_id in record.get("job_ids") or [] if str(job_id).strip()]
    return {
        "schema_version": record.get("schema_version"),
        "artifact_kind": record.get("artifact_kind"),
        "session_id": record.get("session_id"),
        "title": record.get("title") or "Untitled session",
        "title_source": record.get("title_source") or "generated",
        "created_at_utc": record.get("created_at_utc"),
        "updated_at_utc": record.get("updated_at_utc"),
        "status": record.get("status") or "created",
        "provider": record.get("provider"),
        "provider_label": record.get("provider_label"),
        "model": record.get("model"),
        "model_bindings": record.get("model_bindings") if isinstance(record.get("model_bindings"), dict) else None,
        "runtime_harness_id": record.get("runtime_harness_id"),
        "harness_definition_revision": record.get("harness_definition_revision"),
        "runtime_harness_name": record.get("runtime_harness_name"),
        "active_job_id": record.get("active_job_id"),
        "latest_job_id": job_ids[-1] if job_ids else None,
        "job_count": len(job_ids),
        "specification_length": len(str(record.get("specification") or "")),
    }


def list_session_summaries(*, sessions_dir: Path, runs_dir: Path) -> list[dict[str, Any]]:
    runs_by_session = session_run_records_by_session(runs_dir)
    sessions: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    if sessions_dir.exists():
        for session_dir in sessions_dir.iterdir():
            if not session_dir.is_dir():
                continue
            record_path = session_dir / SESSION_RECORD_FILENAME
            if not record_path.is_file():
                continue
            try:
                record = read_canonical_session_record(
                    record_path,
                    sessions_dir=sessions_dir,
                )
            except SessionRecordIntegrityError:
                if re.fullmatch(r"[A-Za-z0-9_.-]+", session_dir.name):
                    unavailable.append(
                        {
                            "session_id": session_dir.name,
                            "title": "Unavailable session",
                            "status": "unavailable",
                            "record_available": False,
                            "integrity_error": "session_record_integrity_error",
                        }
                    )
                continue
            session_id = str(record["session_id"])
            payload = session_payload_from_runs(record, runs_by_session.get(session_id, []))
            summary = summarize_session_payload(payload)
            summary["record_available"] = True
            sessions.append(summary)
    sessions.sort(key=lambda item: item.get("updated_at_utc") or item.get("created_at_utc") or "", reverse=True)
    unavailable.sort(key=lambda item: item["session_id"])
    return [*sessions, *unavailable]


def get_modeling_session(
    session_id: str,
    *,
    sessions_dir: Path,
    runs_dir: Path,
) -> dict[str, Any]:
    record = read_session_record(session_id, sessions_dir=sessions_dir)
    entries = session_run_records_by_session(runs_dir).get(session_id, [])
    payload = session_payload_from_runs(record, entries)
    runs: list[dict[str, Any]] = []
    for run_dir, run_record in entries:
        try:
            trace_count: int | None = trace_event_count(
                run_dir / RUN_TRACE_FILENAME
            )
            trace_available = True
        except (OSError, TraceFormatError):
            trace_count = None
            trace_available = False
        summary = summarize_run_record(
            run_record,
            run_dir=run_dir,
            trace_event_count=trace_count,
        )
        summary["trace_available"] = trace_available
        runs.append(summary)
    return {
        "session": payload,
        "summary": summarize_session_payload(payload),
        "runs": runs,
    }


__all__ = [
    "get_modeling_session",
    "list_session_summaries",
    "session_payload_from_runs",
    "session_run_records_by_session",
    "summarize_session_payload",
]
