from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.api.context import AppContext
from backend.api.models import RunRequest
from backend.api.sse import format_sse_message, sse_comment
from backend.persistence.run_trace import (
    DEFAULT_TRACE_PAGE_LIMIT,
    TraceFormatError,
    TraceReadCursor,
    decode_trace_cursor,
    load_trace_page,
    validate_trace,
)
from backend.services.run_cancellation import cancel_run as cancel_run_core
from backend.services.run_coordinator import (
    RunCoordinatorClosedError,
    RunNotFoundError,
    RunSubscription,
    SessionRunConflictError,
    SubscriptionDisconnectedError,
)
from backend.services.run_event_models import TERMINAL_RUN_EVENT_TYPES, RunEventEnvelope
from backend.services.run_queries import (
    TRACE_PAGE_MAX_LIMIT,
    get_run_payload,
    get_run_trace_payload,
    list_run_summaries,
    read_run_record,
)
from backend.services.run_stream_preflight import validated_run_stream_request
from core.statuses import run_status_is_terminal


_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "X-Content-Type-Options": "nosniff",
}


def _run_trace_integrity_error(error: BaseException) -> HTTPException:
    return HTTPException(status_code=409, detail="run_trace_integrity_error")


def _resolved_event_cursor(after: int, last_event_id: str | None) -> int:
    if last_event_id is None:
        return after
    raw_cursor = last_event_id.strip()
    try:
        cursor = int(raw_cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be a non-negative integer.") from exc
    if cursor < 0 or str(cursor) != raw_cursor:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be a non-negative integer.")
    return cursor


def _formatted_envelope(envelope: RunEventEnvelope) -> str:
    return format_sse_message(
        envelope.model_dump(mode="json"),
        event_id=envelope.sequence,
    )


async def _live_event_stream(subscription: RunSubscription) -> AsyncIterator[str]:
    yield sse_comment("stream-open")
    try:
        while True:
            try:
                envelope = await asyncio.wait_for(subscription.receive(), timeout=15.0)
            except asyncio.TimeoutError:
                yield sse_comment("heartbeat")
                continue
            except SubscriptionDisconnectedError:
                break
            yield _formatted_envelope(envelope)
            if envelope.type in TERMINAL_RUN_EVENT_TYPES:
                break
    finally:
        await subscription.aclose()


async def _persisted_event_stream(
    *,
    run_id: str,
    session_id: str | None,
    trace_path: Path,
    after: int,
    high_water: int,
) -> AsyncIterator[str]:
    yield sse_comment("stream-open")
    cursor = after
    read_cursor: TraceReadCursor | None = None
    while cursor < high_water:
        page = await asyncio.to_thread(
            load_trace_page,
            trace_path,
            after=cursor,
            limit=min(DEFAULT_TRACE_PAGE_LIMIT, high_water - cursor),
            cursor=read_cursor,
        )
        if not page.records:
            break
        for record in page.records:
            sequence = int(record["sequence"])
            if sequence > high_water:
                return
            envelope = RunEventEnvelope.from_trace_record(
                run_id=run_id,
                session_id=session_id,
                record=record,
            )
            yield _formatted_envelope(envelope)
            cursor = sequence
        read_cursor = TraceReadCursor(
            sequence=page.next_after,
            byte_offset=page.next_byte_offset,
        )
        if not page.has_more:
            break


def create_router(context: AppContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/runs")
    def list_runs() -> dict[str, Any]:
        return {
            "runs": list_run_summaries(
                runs_dir=context.runs_dir,
                active_run_ids=context.active_runs,
                sessions_dir=context.sessions_dir,
            )
        }

    @router.post("/api/runs", status_code=202)
    async def create_run(request: RunRequest) -> dict[str, Any]:
        coordinator = context.coordinator
        if coordinator is None:
            raise HTTPException(status_code=503, detail="Run coordinator is unavailable.")

        prepared_run = await validated_run_stream_request(
            request,
            runs_dir=context.runs_dir,
            sessions_dir=context.sessions_dir,
            providers_dir=context.provider_catalogs.providers_dir,
        )
        try:
            creation = await coordinator.create_run(prepared_run)
        except SessionRunConflictError as exc:
            detail = f"Session '{exc.session_id}' already has an active run."
            if exc.active_run_id:
                detail = f"{detail} Active run: {exc.active_run_id}."
            raise HTTPException(status_code=409, detail=detail) from exc
        except RunCoordinatorClosedError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        run_id = creation.run_id
        return {
            "run_id": run_id,
            "session_id": creation.session_id,
            "status": creation.status,
            "snapshot_url": f"/api/runs/{run_id}",
            "events_url": f"/api/runs/{run_id}/events",
        }

    @router.get("/api/runs/{job_id}")
    def get_run(job_id: str, include_trace: bool = True) -> dict[str, Any]:
        return get_run_payload(
            job_id,
            runs_dir=context.runs_dir,
            active_run_ids=context.active_runs,
            sessions_dir=context.sessions_dir,
            include_trace=include_trace,
        )

    @router.get("/api/runs/{job_id}/events")
    async def get_run_events(
        job_id: str,
        after: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        cursor = _resolved_event_cursor(after, last_event_id)
        coordinator = context.coordinator
        if coordinator is not None:
            try:
                subscription = await coordinator.subscribe(job_id, after=cursor)
            except RunNotFoundError:
                subscription = None
            except (OSError, TraceFormatError) as exc:
                raise _run_trace_integrity_error(exc) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if subscription is not None:
                return StreamingResponse(
                    _live_event_stream(subscription),
                    media_type="text/event-stream",
                    headers=_SSE_HEADERS,
                )

        run_dir, record = await asyncio.to_thread(read_run_record, job_id, runs_dir=context.runs_dir)
        if not run_status_is_terminal(str(record.get("status") or "")):
            raise HTTPException(
                status_code=409,
                detail="Run is active but is not owned by this coordinator.",
            )
        trace_path = run_dir / "trace.jsonl"
        try:
            high_water = await asyncio.to_thread(validate_trace, trace_path)
        except (OSError, TraceFormatError) as exc:
            raise _run_trace_integrity_error(exc) from exc
        if cursor > high_water:
            raise HTTPException(
                status_code=400,
                detail=f"Run event cursor {cursor} is ahead of the persisted high-water mark {high_water}.",
            )
        session_id = str(record.get("session_id") or "").strip() or None
        return StreamingResponse(
            _persisted_event_stream(
                run_id=job_id,
                session_id=session_id,
                trace_path=trace_path,
                after=cursor,
                high_water=high_water,
            ),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    @router.get("/api/runs/{job_id}/trace")
    def get_run_trace(
        job_id: str,
        after: int | None = Query(default=None, ge=0),
        limit: int | None = Query(default=None, ge=1, le=TRACE_PAGE_MAX_LIMIT),
        cursor: str | None = Query(default=None, min_length=1, max_length=512),
    ) -> dict[str, Any]:
        if cursor is not None and after is not None:
            raise HTTPException(
                status_code=400,
                detail="Use either 'after' or a continuation cursor, not both.",
            )
        try:
            read_cursor = (
                decode_trace_cursor(cursor, run_id=job_id)
                if cursor is not None
                else None
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return get_run_trace_payload(
            job_id,
            runs_dir=context.runs_dir,
            active_run_ids=context.active_runs,
            sessions_dir=context.sessions_dir,
            after=after,
            limit=limit,
            cursor=read_cursor,
        )

    @router.post("/api/runs/{job_id}/cancel")
    async def cancel_run(job_id: str) -> dict[str, Any]:
        coordinator = context.coordinator
        if coordinator is not None:
            try:
                result = await coordinator.cancel(job_id)
            except RunNotFoundError:
                pass
            else:
                return {
                    "run_id": result.run_id,
                    "job_id": result.run_id,
                    "status": result.status,
                    "cancelled": result.cancelled,
                    "persistence_degraded": result.persistence_degraded,
                    "warning": result.warning,
                }
        # Persisted terminal/interrupted runs may outlive the in-memory coordinator.
        legacy_result = cancel_run_core(
            job_id,
            runs_dir=context.runs_dir,
            active_runs=context.active_runs,
        )
        return {
            "run_id": job_id,
            "persistence_degraded": False,
            "warning": None,
            **legacy_result,
        }

    return router
