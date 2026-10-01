from __future__ import annotations

import re
from collections.abc import Container
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.settings import RUN_RECORD_FILENAME, RUN_TRACE_FILENAME
from backend.persistence.locks import run_lock
from backend.persistence.post_run_transaction_guard import (
    PostRunTransactionPendingError,
    pending_post_run_transaction_id,
)
from backend.persistence.run_paths import safe_run_dir
from backend.persistence.run_record_integrity import (
    RunRecordIntegrityError,
    read_canonical_run_record,
)
from backend.persistence.run_specifications import RunSpecificationIntegrityError
from backend.persistence.run_sources import source_run_specification
from backend.persistence.run_records import (
    refresh_archived_plantuml_payloads,
    run_payload_with_final_result,
    summarize_run_record,
)
from backend.persistence.run_trace import (
    DEFAULT_TRACE_PAGE_LIMIT,
    MAX_TRACE_PAGE_LIMIT,
    TraceFormatError,
    TraceReadCursor,
    encode_trace_cursor,
    load_trace,
    load_trace_page,
    trace_event_count,
)
from backend.services.decision_patches import decision_patches_for_run
from backend.services.recorded_patch_policy import (
    RecordedPatchPolicyError,
    recorded_patch_policy,
)


TRACE_PAGE_MAX_LIMIT = MAX_TRACE_PAGE_LIMIT


def _run_trace_integrity_error(error: BaseException) -> HTTPException:
    return HTTPException(status_code=409, detail="run_trace_integrity_error")


def _trace_summary_state(trace_path: Path) -> tuple[int | None, bool]:
    try:
        return trace_event_count(trace_path), True
    except (OSError, TraceFormatError):
        return None, False


def read_run_record(job_id: str, *, runs_dir: Path) -> tuple[Path, dict[str, Any]]:
    run_dir = safe_run_dir(job_id, runs_dir=runs_dir)
    record_path = run_dir / RUN_RECORD_FILENAME
    if not record_path.is_file():
        raise HTTPException(status_code=404, detail="Run not found.")
    try:
        if pending_post_run_transaction_id(run_dir) is not None:
            raise HTTPException(
                status_code=409,
                detail="post_run_transaction_pending",
            )
        return run_dir, read_canonical_run_record(record_path, runs_dir=runs_dir)
    except PostRunTransactionPendingError as exc:
        raise HTTPException(
            status_code=409,
            detail="post_run_transaction_pending",
        ) from exc
    except RunRecordIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="run_record_integrity_error",
        ) from exc


def list_run_summaries(
    *,
    runs_dir: Path,
    active_run_ids: Container[str],
    sessions_dir: Path | None = None,
) -> list[dict[str, Any]]:
    # Kept in the query contract while callers migrate away from inferring
    # persisted status from this process's worker registry. Queries are
    # intentionally read-only; startup reconciliation owns stale records.
    _ = active_run_ids, sessions_dir
    runs: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    if runs_dir.exists():
        for run_dir in runs_dir.iterdir():
            if not run_dir.is_dir():
                continue
            record_path = run_dir / RUN_RECORD_FILENAME
            if not record_path.is_file():
                continue
            try:
                if pending_post_run_transaction_id(run_dir) is not None:
                    raise PostRunTransactionPendingError(
                        "Post-run transaction is pending."
                    )
                record = read_canonical_run_record(record_path, runs_dir=runs_dir)
            except (PostRunTransactionPendingError, RunRecordIntegrityError) as exc:
                if re.fullmatch(r"[A-Za-z0-9_.-]+", run_dir.name):
                    pending = isinstance(
                        exc,
                        PostRunTransactionPendingError,
                    )
                    unavailable.append(
                        {
                            "job_id": run_dir.name,
                            "status": "unavailable",
                            "record_available": False,
                            "trace_available": False,
                            "integrity_error": (
                                "post_run_transaction_pending"
                                if pending
                                else "run_record_integrity_error"
                            ),
                        }
                    )
                continue
            trace_count, trace_available = _trace_summary_state(
                run_dir / RUN_TRACE_FILENAME
            )
            summary = summarize_run_record(
                record,
                run_dir=run_dir,
                trace_event_count=trace_count,
            )
            summary["record_available"] = True
            summary["trace_available"] = trace_available
            runs.append(summary)
    runs.sort(key=lambda item: item.get("started_at_utc") or "", reverse=True)
    unavailable.sort(key=lambda item: item["job_id"])
    return [*runs, *unavailable]


def get_run_payload(
    job_id: str,
    *,
    runs_dir: Path,
    active_run_ids: Container[str],
    sessions_dir: Path | None = None,
    include_trace: bool = True,
) -> dict[str, Any]:
    """Read a reducer-safe snapshot and its persisted event high-water mark.

    Trace appends and canonical record/result writes use the same re-entrant
    run lock.  Holding it across this read prevents a snapshot from advertising
    a sequence newer than the state included in that snapshot.
    """

    run_dir = safe_run_dir(job_id, runs_dir=runs_dir)
    with run_lock(run_dir):
        payload = _get_run_payload_unlocked(
            job_id,
            runs_dir=runs_dir,
            active_run_ids=active_run_ids,
            sessions_dir=sessions_dir,
            include_trace=include_trace,
        )
        try:
            snapshot_sequence = trace_event_count(run_dir / RUN_TRACE_FILENAME)
        except (OSError, TraceFormatError) as exc:
            raise _run_trace_integrity_error(exc) from exc
        payload["snapshot_sequence"] = snapshot_sequence
        run_payload = payload.get("run")
        if isinstance(run_payload, dict):
            run_payload["snapshot_sequence"] = snapshot_sequence
        return payload


def _get_run_payload_unlocked(
    job_id: str,
    *,
    runs_dir: Path,
    active_run_ids: Container[str],
    sessions_dir: Path | None = None,
    include_trace: bool = True,
) -> dict[str, Any]:
    _ = active_run_ids, sessions_dir
    run_dir, record = read_run_record(job_id, runs_dir=runs_dir)
    trace_path = run_dir / RUN_TRACE_FILENAME
    try:
        trace = load_trace(trace_path) if include_trace else []
        trace_count = len(trace) if include_trace else trace_event_count(trace_path)
    except (OSError, TraceFormatError) as exc:
        raise _run_trace_integrity_error(exc) from exc
    if include_trace:
        refresh_archived_plantuml_payloads(run_dir, record, trace)
    summary = summarize_run_record(
        record,
        run_dir=run_dir,
        trace_event_count=trace_count,
    )
    summary["trace_available"] = True
    try:
        patch_policy = recorded_patch_policy(record)
    except RecordedPatchPolicyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    decision_patches = decision_patches_for_run(
        run_dir,
        record,
        name_policy=patch_policy.name_policy,
    )
    run_payload = run_payload_with_final_result(record, run_dir)
    try:
        run_payload["specification"] = source_run_specification(run_dir, record)
    except RunSpecificationIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="run_specification_integrity_error",
        ) from exc
    run_payload["runtime_harness_id"] = summary.get("runtime_harness_id")
    run_payload["runtime_harness_name"] = summary.get("runtime_harness_name")
    run_payload["resume_checkpoint_stage"] = summary.get("resume_checkpoint_stage")
    run_payload["resumable"] = summary.get("resumable")
    run_payload["decision_patches"] = decision_patches
    return {
        "run": run_payload,
        "summary": summary,
        "trace": trace,
        "decision_patches": decision_patches,
    }


def get_run_trace_payload(
    job_id: str,
    *,
    runs_dir: Path,
    active_run_ids: Container[str],
    sessions_dir: Path | None = None,
    after: int | None = None,
    limit: int | None = None,
    cursor: TraceReadCursor | None = None,
) -> dict[str, Any]:
    _ = active_run_ids, sessions_dir
    run_dir, record = read_run_record(job_id, runs_dir=runs_dir)
    trace_path = run_dir / RUN_TRACE_FILENAME
    try:
        if after is None and limit is None and cursor is None:
            # Compatibility path for the current frontend. New callers should use
            # a bounded cursor page and avoid materializing an archived trace.
            trace = load_trace(trace_path)
            pagination: dict[str, Any] = {}
        else:
            page = load_trace_page(
                trace_path,
                after=cursor.sequence if cursor is not None else (0 if after is None else after),
                limit=DEFAULT_TRACE_PAGE_LIMIT if limit is None else limit,
                cursor=cursor,
            )
            trace = page.records
            pagination = {
                "after": page.after,
                "limit": page.limit,
                "next_after": page.next_after,
                "next_cursor": (
                    encode_trace_cursor(
                        job_id,
                        TraceReadCursor(
                            sequence=page.next_after,
                            byte_offset=page.next_byte_offset,
                        ),
                    )
                    if page.has_more and page.records
                    else None
                ),
                "has_more": page.has_more,
            }
        trace_count = trace_event_count(trace_path)
    except (OSError, TraceFormatError) as exc:
        raise _run_trace_integrity_error(exc) from exc
    refresh_archived_plantuml_payloads(run_dir, record, trace)
    summary = summarize_run_record(
        record,
        run_dir=run_dir,
        trace_event_count=trace_count,
    )
    summary["trace_available"] = True
    return {"job_id": job_id, "summary": summary, "trace": trace, **pagination}


__all__ = [
    "TRACE_PAGE_MAX_LIMIT",
    "get_run_payload",
    "get_run_trace_payload",
    "list_run_summaries",
    "read_run_record",
]
