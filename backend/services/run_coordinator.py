from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from backend.persistence.common import utc_now_iso
from backend.persistence.run_records import summarize_run_record
from backend.persistence.run_trace import (
    DEFAULT_TRACE_PAGE_LIMIT,
    TracePage,
    TraceReadCursor,
    append_trace_event,
    load_trace_page,
)
from backend.persistence.session_jobs import attach_job_to_session
from backend.persistence.session_records import read_session_record
from backend.services.active_run_registry import ACTIVE_RUNS, ActiveRun
from backend.services.async_file_work import (
    finish_shielded_task,
    run_thread_to_completion,
)
from backend.services.prepared_run import PreparedRun
from backend.services.run_event_models import TERMINAL_RUN_EVENT_TYPES, RunEventEnvelope
from backend.services.run_stream_events import RunStreamEventBus
from backend.services.run_stream_generation import ActiveGenerationTracker
from backend.services.run_stream_records import (
    RunStreamRecordContext,
    create_run_stream_record,
    mutate_run_stream_record,
    run_stream_start_payload,
)
from backend.services.run_stream_worker import run_stream_worker
from backend.services.run_worker_outcome import RunWorkerOutcome
from backend.services.run_operation_registry import (
    RunOperationAdmissionPausedError,
    RunOperationConflictError,
    RunOperationHandle,
    RunOperationRegistry,
    RunOperationRegistryClosedError,
)
from backend.services.shutdown_deadline import ShutdownDeadline, consume_task_result
from core.config_safety import redact_persisted_value, redact_sensitive_text, safe_exception_detail
from core.statuses import (
    RUN_STATUS_CANCELLED,
    RUN_STATUS_CANCELLING,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_INTERRUPTED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    run_status_is_terminal,
)


WorkerFactory = Callable[
    [RunStreamRecordContext, RunStreamEventBus, MutableMapping[str, ActiveRun]],
    Awaitable[RunWorkerOutcome | None],
]
RecordFactory = Callable[[PreparedRun], RunStreamRecordContext]
TracePageLoader = Callable[..., TracePage]
LOGGER = logging.getLogger(__name__)

_TERMINAL_EVENT_FOR_STATUS: Final[dict[str, str]] = {
    RUN_STATUS_COMPLETED: "done",
    RUN_STATUS_FAILED: "error",
    RUN_STATUS_CANCELLED: "cancelled",
    RUN_STATUS_INTERRUPTED: "cancelled",
}
_DEFAULT_CLEANUP_RETRY_DELAYS: Final[tuple[float, ...]] = (0.0, 0.1, 0.5, 2.0)


class RunCoordinatorError(RuntimeError):
    pass


class RunCoordinatorClosedError(RunCoordinatorError):
    pass


class RunAdmissionPausedError(RunCoordinatorClosedError):
    pass


class RunNotFoundError(RunCoordinatorError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Run {run_id!r} is not known to this coordinator.")


class SessionRunConflictError(RunCoordinatorError):
    def __init__(self, session_id: str, active_run_id: str | None) -> None:
        self.session_id = session_id
        self.active_run_id = active_run_id
        detail = f"Session {session_id!r} already owns an active run"
        if active_run_id:
            detail += f" ({active_run_id})"
        super().__init__(detail + ".")


class SubscriptionDisconnectedError(RunCoordinatorError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Run event subscription disconnected: {reason}.")


class TraceSequenceError(RunCoordinatorError):
    pass


class RunTerminalEventError(RunCoordinatorError):
    def __init__(self, run_id: str, terminal_event_type: str) -> None:
        self.run_id = run_id
        self.terminal_event_type = terminal_event_type
        super().__init__(
            f"Run {run_id!r} already emitted terminal event {terminal_event_type!r}."
        )


@dataclass(frozen=True, slots=True)
class RunCreation:
    run_id: str
    session_id: str | None
    status: str
    record_path: Path
    trace_path: Path


@dataclass(frozen=True, slots=True)
class CancellationResult:
    run_id: str
    status: str
    cancelled: bool
    persistence_degraded: bool = False
    warning: str | None = None


@dataclass(frozen=True, slots=True)
class ShutdownResult:
    cancelled_run_ids: tuple[str, ...]
    unfinished_run_ids: tuple[str, ...]
    unfinished_operation_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _SubscriptionClosed:
    reason: str


_SubscriptionItem = RunEventEnvelope | _SubscriptionClosed


@dataclass(slots=True)
class _RunRuntime:
    context: RunStreamRecordContext
    operation_handle: RunOperationHandle
    start_gate: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None
    last_published_sequence: int = 0
    terminal_event_type: str | None = None
    terminal_status: str | None = None
    terminal_event_payload: dict[str, Any] | None = None
    pending_terminal_record: dict[str, Any] | None = None
    cancellation_requested: bool = False
    subscribers: dict[int, RunSubscription] = field(default_factory=dict)
    publication_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass(frozen=True, slots=True)
class _DegradedRun:
    runtime: _RunRuntime
    task: asyncio.Task[None]
    attempts: int
    detected_at_utc: str
    last_error_type: str

    def health_summary(self) -> dict[str, Any]:
        return {
            "run_id": self.runtime.context.job_id,
            "reason": "terminal_persistence_failed",
            "attempts": self.attempts,
            "detected_at_utc": self.detected_at_utc,
            "error_type": self.last_error_type,
        }


class RunSubscription:
    """One replay-first view over a run's persisted event stream."""

    def __init__(
        self,
        *,
        coordinator: RunCoordinator,
        run_id: str,
        subscription_id: int,
        high_water: int,
        replay: list[RunEventEnvelope],
        queue_size: int,
    ) -> None:
        self.run_id = run_id
        self.subscription_id = subscription_id
        self.high_water = high_water
        self._coordinator = coordinator
        self._replay = deque(replay)
        self._queue: asyncio.Queue[_SubscriptionItem] = asyncio.Queue(maxsize=queue_size)
        self._closed = False
        self._terminal_delivered = False
        self.last_delivered_sequence = replay[0].sequence - 1 if replay else high_water

    def __aiter__(self) -> RunSubscription:
        return self

    async def __anext__(self) -> RunEventEnvelope:
        try:
            return await self.receive()
        except SubscriptionDisconnectedError:
            raise StopAsyncIteration from None

    async def receive(self) -> RunEventEnvelope:
        if self._terminal_delivered:
            await self.aclose()
            raise SubscriptionDisconnectedError("terminal")
        if self._replay:
            event = self._replay.popleft()
        else:
            item = await self._queue.get()
            if isinstance(item, _SubscriptionClosed):
                self._closed = True
                raise SubscriptionDisconnectedError(item.reason)
            event = item
        self.last_delivered_sequence = event.sequence
        if event.type in TERMINAL_RUN_EVENT_TYPES:
            self._terminal_delivered = True
        return event

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._coordinator.unsubscribe(self.run_id, self.subscription_id)

    def _enqueue(self, event: RunEventEnvelope) -> bool:
        if self._closed:
            return False
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            return False

    def _force_close(self, reason: str) -> None:
        if self._closed:
            return
        self._closed = True
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        try:
            self._queue.put_nowait(_SubscriptionClosed(reason))
        except asyncio.QueueFull:  # pragma: no cover - queue was just drained
            pass


async def _default_worker(
    context: RunStreamRecordContext,
    event_bus: RunStreamEventBus,
    active_runs: MutableMapping[str, ActiveRun],
) -> RunWorkerOutcome:
    return await run_stream_worker(context, event_bus=event_bus, active_runs=active_runs)


def _interrupt_unscheduled_run(
    context: RunStreamRecordContext,
    *,
    error: str = "Run creation was cancelled before the worker was scheduled.",
    reason: str = "run_creation_cancelled",
) -> None:
    try:
        def interrupt(latest: dict[str, Any]) -> None:
            if run_status_is_terminal(str(latest.get("status") or "")):
                return
            latest.update(
                status=RUN_STATUS_INTERRUPTED,
                completed_at_utc=utc_now_iso(),
                error=redact_sensitive_text(error),
                interruption_reason=reason,
            )

        mutate_run_stream_record(context, interrupt)
    except Exception:
        # Preserve cancellation; startup reconciliation repairs a queued
        # record if this final atomic write fails.
        pass


class RunCoordinator:
    """Own background run tasks independently from their SSE subscribers.

    This is deliberately a small lifecycle coordinator, not a workflow engine.
    Harness ordering stays in the harness layer; this service only reserves a
    session, schedules its worker, durably sequences events, and fans them out.
    """

    def __init__(
        self,
        *,
        runs_dir: Path,
        sessions_dir: Path | None,
        active_runs: MutableMapping[str, ActiveRun] | None = None,
        operation_registry: RunOperationRegistry | None = None,
        worker_factory: WorkerFactory | None = None,
        record_factory: RecordFactory | None = None,
        trace_page_loader: TracePageLoader = load_trace_page,
        subscriber_queue_size: int = 256,
        shutdown_timeout: float = 5.0,
        cleanup_retry_delays: tuple[float, ...] = _DEFAULT_CLEANUP_RETRY_DELAYS,
    ) -> None:
        if subscriber_queue_size < 1:
            raise ValueError("subscriber_queue_size must be positive.")
        if shutdown_timeout < 0:
            raise ValueError("shutdown_timeout must be non-negative.")
        if not cleanup_retry_delays or any(delay < 0 for delay in cleanup_retry_delays):
            raise ValueError("cleanup_retry_delays must contain non-negative delays.")
        self._runs_dir = Path(runs_dir)
        self._sessions_dir = Path(sessions_dir) if sessions_dir is not None else None
        self._active_runs = active_runs if active_runs is not None else ACTIVE_RUNS
        self._operation_registry = operation_registry or RunOperationRegistry()
        self._worker_factory = worker_factory or _default_worker
        self._trace_page_loader = trace_page_loader
        self._subscriber_queue_size = subscriber_queue_size
        self._shutdown_timeout = shutdown_timeout
        self._cleanup_retry_delays = tuple(float(delay) for delay in cleanup_retry_delays)
        if record_factory is None:
            self._record_factory = lambda prepared_run: create_run_stream_record(
                prepared_run,
                runs_dir=self._runs_dir,
                sessions_dir=self._sessions_dir,
                initial_status=RUN_STATUS_QUEUED,
            )
        else:
            self._record_factory = record_factory

        self._lock = asyncio.Lock()
        self._runs: dict[str, _RunRuntime] = {}
        self._next_subscription_id = 1
        self._cleanup_tasks: dict[str, asyncio.Task[None]] = {}
        self._degraded_runs: dict[str, _DegradedRun] = {}
        self._shutdown_deadline: ShutdownDeadline | None = None

    @property
    def active_runs(self) -> MutableMapping[str, ActiveRun]:
        return self._active_runs

    @property
    def operation_registry(self) -> RunOperationRegistry:
        return self._operation_registry

    @property
    def shutdown_timeout(self) -> float:
        return self._shutdown_timeout

    async def startup(self) -> None:
        await self._operation_registry.startup()

    async def health_snapshot(self) -> dict[str, Any]:
        operation_health = await self._operation_registry.health_snapshot()
        async with self._lock:
            summaries = [
                entry.health_summary()
                for _run_id, entry in sorted(self._degraded_runs.items())
            ][:20]
            degraded_count = len(self._degraded_runs)
            return {
                "status": "degraded" if degraded_count else "ok",
                **operation_health,
                "degraded_count": degraded_count,
                "degraded_runs": summaries,
            }

    async def create_run(
        self,
        prepared_run: PreparedRun,
    ) -> RunCreation:
        session_id = str(prepared_run.session_id or "").strip() or None
        try:
            operation = await self._operation_registry.claim_generation(session_id)
        except RunOperationAdmissionPausedError as exc:
            raise RunAdmissionPausedError(str(exc)) from exc
        except RunOperationRegistryClosedError as exc:
            raise RunCoordinatorClosedError(str(exc)) from exc
        except RunOperationConflictError as exc:
            raise SessionRunConflictError(
                session_id or exc.session_id or "",
                exc.active_run_id,
            ) from exc

        def create_reserved_record() -> RunStreamRecordContext:
            # Session deletion uses the same operation reservation. Recheck
            # existence after acquiring it so request preflight cannot race a
            # completed deletion and publish an orphan run.
            if session_id and self._sessions_dir is not None:
                read_session_record(session_id, sessions_dir=self._sessions_dir)
            return self._record_factory(prepared_run)

        record_task = asyncio.create_task(asyncio.to_thread(create_reserved_record))
        try:
            context = await asyncio.shield(record_task)
        except asyncio.CancelledError as cancellation:
            context = None
            try:
                context = await finish_shielded_task(record_task)
            except BaseException:
                pass
            if context is not None:
                await self._fail_published_creation(
                    context,
                    operation=operation,
                    error="Run creation was cancelled before the worker was scheduled.",
                    reason="run_creation_cancelled",
                )
            else:
                await operation.finish()
            raise cancellation
        except BaseException:
            await operation.finish()
            raise

        provisional_task: asyncio.Task[None] | None = None
        try:
            await self._update_session_index_best_effort(context)
            async with self._lock:
                if context.job_id in self._runs or context.job_id in self._active_runs:
                    raise RunCoordinatorError(f"Duplicate run id {context.job_id!r}.")
            runtime = _RunRuntime(context=context, operation_handle=operation)
            provisional_task = self._create_worker_task(runtime)
            runtime.task = provisional_task
            await operation.activate_generation(
                run_id=context.job_id,
                task=provisional_task,
            )
            async with self._lock:
                if context.job_id in self._runs or context.job_id in self._active_runs:
                    raise RunCoordinatorError(f"Duplicate run id {context.job_id!r}.")
                active_run = ActiveRun(
                    job_id=context.job_id,
                    task=provisional_task,
                    record_path=context.record_path,
                    trace_path=context.trace_path,
                    session_id=session_id,
                )
                provisional_task.add_done_callback(
                    lambda finished, run_id=context.job_id: self._schedule_task_cleanup(
                        run_id,
                        finished,
                    )
                )
                self._runs[context.job_id] = runtime
                self._active_runs[context.job_id] = active_run
            runtime.start_gate.set()
        except RunOperationAdmissionPausedError as exc:
            await self._fail_published_creation(
                context,
                operation=operation,
                provisional_task=provisional_task,
                error="Run admission was paused before the worker was scheduled.",
                reason="run_creation_admission_paused",
            )
            raise RunAdmissionPausedError(str(exc)) from exc
        except RunOperationRegistryClosedError as exc:
            await self._fail_published_creation(
                context,
                operation=operation,
                provisional_task=provisional_task,
                error="Run coordinator stopped before the worker was scheduled.",
                reason="run_creation_coordinator_closed",
            )
            raise RunCoordinatorClosedError(str(exc)) from exc
        except asyncio.CancelledError as cancellation:
            await self._fail_published_creation(
                context,
                operation=operation,
                provisional_task=provisional_task,
                error="Run creation was cancelled before the worker was scheduled.",
                reason="run_creation_cancelled",
            )
            raise cancellation
        except BaseException as exc:
            detail = safe_exception_detail(exc)
            await self._fail_published_creation(
                context,
                operation=operation,
                provisional_task=provisional_task,
                error=f"Run could not be scheduled: {detail}",
                reason="run_creation_failed",
            )
            raise

        return RunCreation(
            run_id=context.job_id,
            session_id=session_id,
            status=RUN_STATUS_QUEUED,
            record_path=context.record_path,
            trace_path=context.trace_path,
        )

    async def _run_worker_after_start(
        self,
        runtime: _RunRuntime,
    ) -> None:
        await runtime.start_gate.wait()
        await self._run_worker(runtime)

    def _create_worker_task(self, runtime: _RunRuntime) -> asyncio.Task[None]:
        return asyncio.create_task(
            self._run_worker_after_start(runtime),
            name=f"run-worker:{runtime.context.job_id}",
        )

    async def _update_session_index_best_effort(
        self,
        context: RunStreamRecordContext,
    ) -> None:
        index_task = asyncio.create_task(
            asyncio.to_thread(
                attach_job_to_session,
                context.prepared_run.session_id,
                context.job_id,
                sessions_dir=context.sessions_dir,
            ),
            name=f"run-session-index:{context.job_id}",
        )
        try:
            await asyncio.shield(index_task)
        except asyncio.CancelledError as cancellation:
            try:
                await finish_shielded_task(index_task)
            except Exception as exc:
                self._warn_session_index_failure(context.job_id, exc)
            raise cancellation
        except Exception as exc:
            self._warn_session_index_failure(context.job_id, exc)

    @staticmethod
    def _warn_session_index_failure(run_id: str, exc: Exception) -> None:
        LOGGER.warning(
            "Run %s was published, but its rebuildable session index could not be updated: %s",
            run_id,
            safe_exception_detail(exc),
        )

    async def _fail_published_creation(
        self,
        context: RunStreamRecordContext,
        *,
        operation: RunOperationHandle,
        provisional_task: asyncio.Task[None] | None = None,
        error: str,
        reason: str,
    ) -> None:
        tasks: set[asyncio.Task[None]] = set()
        if provisional_task is not None:
            tasks.add(provisional_task)
        async with self._lock:
            runtime = self._runs.get(context.job_id)
            if runtime is not None and runtime.context is context:
                if runtime.task is not None:
                    tasks.add(runtime.task)
                self._runs.pop(context.job_id, None)
            active = self._active_runs.get(context.job_id)
            if active is not None and active.record_path == context.record_path:
                tasks.add(active.task)
                self._active_runs.pop(context.job_id, None)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await operation.finish()

        interruption_task = asyncio.create_task(
            asyncio.to_thread(
                _interrupt_unscheduled_run,
                context,
                error=error,
                reason=reason,
            ),
            name=f"run-creation-interruption:{context.job_id}",
        )
        try:
            await asyncio.shield(interruption_task)
        except asyncio.CancelledError:
            await finish_shielded_task(interruption_task)

    async def delete_session_when_idle(
        self,
        session_id: str,
        deletion: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        """Block run admission while an idle session is being deleted."""

        try:
            operation = await self._operation_registry.claim_session_deletion(session_id)
        except RunOperationConflictError as exc:
            raise SessionRunConflictError(session_id, exc.active_run_id) from exc
        except RunOperationAdmissionPausedError as exc:
            raise RunAdmissionPausedError(str(exc)) from exc
        except RunOperationRegistryClosedError as exc:
            raise RunCoordinatorClosedError(str(exc)) from exc
        deletion_task = asyncio.create_task(asyncio.to_thread(deletion))
        try:
            return await asyncio.shield(deletion_task)
        except asyncio.CancelledError as cancellation:
            # Cancelling this coroutine cannot stop filesystem work already
            # running in a thread. Keep the reservation until that work has
            # actually stopped before propagating cancellation.
            try:
                await finish_shielded_task(deletion_task)
            except BaseException:
                pass
            raise cancellation
        finally:
            await operation.finish()

    async def emit(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        timestamp_utc: str | None = None,
    ) -> RunEventEnvelope:
        async with self._lock:
            runtime = self._runtime(run_id)
        async with runtime.publication_lock:
            async with self._lock:
                if self._runs.get(run_id) is not runtime:
                    raise RunNotFoundError(run_id)
                if runtime.terminal_event_type is not None:
                    raise RunTerminalEventError(run_id, runtime.terminal_event_type)
            append_task = asyncio.create_task(
                asyncio.to_thread(
                    append_trace_event,
                    runtime.context.trace_path,
                    event=event_type,
                    payload=payload,
                    timestamp_utc=timestamp_utc,
                ),
                name=f"run-event-append:{run_id}",
            )
            cancellation: asyncio.CancelledError | None = None
            try:
                record = await asyncio.shield(append_task)
            except asyncio.CancelledError as exc:
                cancellation = exc
                record = await finish_shielded_task(append_task)
            async with self._lock:
                if self._runs.get(run_id) is not runtime:
                    raise RunNotFoundError(run_id)
                envelope = self._publish_record_locked(runtime, record)
            if cancellation is not None:
                raise cancellation
            return envelope

    async def subscribe(self, run_id: str, *, after: int = 0) -> RunSubscription:
        if isinstance(after, bool) or not isinstance(after, int) or after < 0:
            raise ValueError("Run event cursor must be a non-negative integer.")
        async with self._lock:
            runtime = self._runtime(run_id)
        async with runtime.publication_lock:
            async with self._lock:
                if self._runs.get(run_id) is not runtime:
                    raise RunNotFoundError(run_id)
                high_water = runtime.last_published_sequence
                if after > high_water:
                    raise ValueError(
                        f"Run event cursor {after} is ahead of the persisted high-water mark {high_water}."
                    )
                subscription_id = self._next_subscription_id
                self._next_subscription_id += 1
                subscription = RunSubscription(
                    coordinator=self,
                    run_id=run_id,
                    subscription_id=subscription_id,
                    high_water=high_water,
                    replay=[],
                    queue_size=self._subscriber_queue_size,
                )
                if runtime.terminal_event_type is not None and after == high_water:
                    # A reconnect after acknowledging the terminal event has no
                    # replay and can never receive another live event. Complete
                    # it immediately instead of leaving the HTTP stream hanging.
                    subscription._terminal_delivered = True
                runtime.subscribers[subscription_id] = subscription

        try:
            replay_records = await self._load_trace_records(
                runtime.context.trace_path,
                after=after,
                through=high_water,
            )
            replay = [self._envelope(runtime, record) for record in replay_records]
            subscription._replay.extend(replay)
            if replay:
                subscription.last_delivered_sequence = replay[0].sequence - 1
            else:
                subscription.last_delivered_sequence = high_water
            return subscription
        except BaseException:
            await self.unsubscribe(run_id, subscription_id)
            raise

    async def unsubscribe(self, run_id: str, subscription_id: int) -> None:
        async with self._lock:
            runtime = self._runs.get(run_id)
            if runtime is not None:
                runtime.subscribers.pop(subscription_id, None)

    async def cancel(self, run_id: str) -> CancellationResult:
        async with self._lock:
            runtime = self._runtime(run_id)
        async with runtime.publication_lock:
            async with self._lock:
                if self._runs.get(run_id) is not runtime:
                    raise RunNotFoundError(run_id)
                task = runtime.task
                current_status = str(runtime.context.run_record.get("status") or "unknown")
                if run_status_is_terminal(current_status) or task is None or task.done():
                    return CancellationResult(
                        run_id=run_id,
                        status=current_status,
                        cancelled=False,
                    )
                if current_status == RUN_STATUS_CANCELLING:
                    return CancellationResult(
                        run_id=run_id,
                        status=RUN_STATUS_CANCELLING,
                        cancelled=False,
                    )
                # Stopping paid/provider work is authoritative once this live
                # runtime has been validated. Persistence below may degrade,
                # but must never prevent cancellation from reaching the task.
                runtime.cancellation_requested = True
            operation_cancellation = await runtime.operation_handle.request_cancel()
            if not operation_cancellation.cancellation_requested:
                runtime.cancellation_requested = False
                return CancellationResult(
                    run_id=run_id,
                    status=current_status,
                    cancelled=False,
                )
            requested_at = utc_now_iso()
            cancellation: asyncio.CancelledError | None = None
            persistence_failures: list[tuple[str, Exception]] = []

            def request_cancellation(latest: dict[str, Any]) -> None:
                # A terminal persistence mutation that won the race must not
                # be rolled back to cancelling by a stale in-memory snapshot.
                if run_status_is_terminal(str(latest.get("status") or "unknown")):
                    return
                latest.update(
                    status=RUN_STATUS_CANCELLING,
                    cancel_requested_at_utc=requested_at,
                    error="Cancellation requested by user.",
                )

            mutation_task = asyncio.create_task(
                asyncio.to_thread(
                    mutate_run_stream_record,
                    runtime.context,
                    request_cancellation,
                ),
                name=f"run-cancellation-mutation:{run_id}",
            )
            try:
                await asyncio.shield(mutation_task)
            except asyncio.CancelledError as exc:
                cancellation = exc
                try:
                    await finish_shielded_task(mutation_task)
                except Exception as persistence_error:
                    persistence_failures.append(("run record", persistence_error))
            except Exception as persistence_error:
                persistence_failures.append(("run record", persistence_error))

            append_task = asyncio.create_task(
                asyncio.to_thread(
                    append_trace_event,
                    runtime.context.trace_path,
                    event="cancel_requested",
                    payload={
                        "job_id": run_id,
                        "requested_at_utc": requested_at,
                        "detail": "Cancellation requested by user.",
                    },
                    timestamp_utc=requested_at,
                ),
                name=f"run-cancellation-append:{run_id}",
            )
            record: dict[str, Any] | None = None
            try:
                record = await asyncio.shield(append_task)
            except asyncio.CancelledError as exc:
                cancellation = cancellation or exc
                try:
                    record = await finish_shielded_task(append_task)
                except Exception as persistence_error:
                    persistence_failures.append(("trace", persistence_error))
            except Exception as persistence_error:
                persistence_failures.append(("trace", persistence_error))
            if record is not None:
                try:
                    async with self._lock:
                        if self._runs.get(run_id) is runtime:
                            self._publish_record_locked(runtime, record)
                except Exception as persistence_error:
                    persistence_failures.append(("trace publication", persistence_error))
            for stage, persistence_error in persistence_failures:
                LOGGER.warning(
                    "Cancellation %s bookkeeping failed for run %s (%s).",
                    stage,
                    run_id,
                    type(persistence_error).__name__,
                )
            if cancellation is not None:
                raise cancellation
            persistence_degraded = bool(persistence_failures)
            return CancellationResult(
                run_id=run_id,
                status=RUN_STATUS_CANCELLING,
                cancelled=True,
                persistence_degraded=persistence_degraded,
                warning=(
                    "Provider work was stopped, but local cancellation metadata "
                    "could not be fully persisted. Restart the app to run recovery."
                    if persistence_degraded
                    else None
                ),
            )

    async def shutdown(
        self,
        timeout: float | None = None,
        *,
        deadline: ShutdownDeadline | None = None,
    ) -> ShutdownResult:
        if timeout is not None and deadline is not None:
            raise ValueError("Pass either timeout or deadline, not both.")
        if deadline is None:
            deadline = ShutdownDeadline.after(
                self._shutdown_timeout if timeout is None else timeout,
            )
        self._shutdown_deadline = deadline
        await self._operation_registry.begin_shutdown()
        async with self._lock:
            newly_cancelled_run_ids = [
                run_id
                for run_id, runtime in self._runs.items()
                if (
                    runtime.task is not None
                    and not runtime.task.done()
                    and not runtime.cancellation_requested
                )
            ]
            run_ids = [
                run_id
                for run_id, runtime in self._runs.items()
                if runtime.task is not None and not runtime.task.done()
            ]

        cancellation_tasks: dict[str, asyncio.Task[CancellationResult]] = {}
        if not deadline.expired:
            cancellation_tasks = {
                run_id: asyncio.create_task(
                    self.cancel(run_id),
                    name=f"run-shutdown-cancel:{run_id}",
                )
                for run_id in run_ids
            }
            completed_cancellations, pending_cancellations = await deadline.wait(
                cancellation_tasks.values()
            )
            for task in completed_cancellations:
                try:
                    task.result()
                except RunNotFoundError:
                    # A worker can finish and be evicted between the shutdown
                    # snapshot and its cancellation bookkeeping.
                    pass
                except asyncio.CancelledError:
                    pass
                except Exception as error:
                    LOGGER.warning(
                        "Shutdown cancellation bookkeeping failed (%s).",
                        type(error).__name__,
                    )
            for task in pending_cancellations:
                task.cancel()
                task.add_done_callback(consume_task_result)

        async with self._lock:
            tasks = [
                runtime.task
                for run_id, runtime in self._runs.items()
                if run_id in run_ids and runtime.task is not None
            ]
        pending: set[asyncio.Task[None]] = set()
        if tasks:
            _done, pending = await deadline.wait(tasks)

        # A task that completed before (or during) shutdown still needs its
        # synchronized terminal repair before it can leave the active-only maps.
        # Cleanup tasks are deliberately distinct from best-effort relays and
        # are never cancelled by shutdown.
        if not deadline.expired:
            async with self._lock:
                completed = [
                    (run_id, runtime.task)
                    for run_id, runtime in self._runs.items()
                    if runtime.task is not None and runtime.task.done()
                ]
            for run_id, task in completed:
                self._schedule_task_cleanup(run_id, task)

        cleanup_tasks = tuple(self._cleanup_tasks.values())
        if cleanup_tasks and not deadline.expired:
            await deadline.wait(cleanup_tasks)
        if self._degraded_runs and not deadline.expired:
            await self._retry_degraded_during_shutdown(deadline)

        operation_result = await self._operation_registry.shutdown(
            deadline,
            initiate=False,
        )
        async with self._lock:
            unfinished_ids = tuple(sorted(self._runs))

        return ShutdownResult(
            cancelled_run_ids=tuple(sorted(newly_cancelled_run_ids)),
            unfinished_run_ids=unfinished_ids,
            unfinished_operation_ids=operation_result.unfinished_operation_ids,
        )

    async def _run_worker(self, runtime: _RunRuntime) -> None:
        context = runtime.context
        run_id = context.job_id
        try:
            started_at = utc_now_iso()
            context.started_at_utc = started_at
            start_status = await self._persist_worker_start(context, started_at)
            if start_status == RUN_STATUS_CANCELLING:
                raise asyncio.CancelledError
            if run_status_is_terminal(start_status):
                await self._ensure_terminal_event(runtime, start_status)
                return
            if start_status != RUN_STATUS_RUNNING:
                raise RunCoordinatorError(
                    f"Run {run_id!r} cannot start from status {start_status!r}."
                )
            await self.emit(
                run_id,
                "start",
                run_stream_start_payload(context),
                timestamp_utc=started_at,
            )
            generation_tracker = ActiveGenerationTracker()
            event_bus = RunStreamEventBus(
                generation_tracker=generation_tracker,
                event_publisher=lambda event, payload: self.emit(run_id, event, payload),
                run_dir=context.run_dir,
            )
            outcome = await self._worker_factory(context, event_bus, self._active_runs)
            if not await runtime.operation_handle.begin_finalizing():
                raise asyncio.CancelledError
            if outcome is None:
                # Test and embedding workers may use a bare successful return;
                # the production worker always returns a typed outcome.
                status = await self._persist_worker_completion(
                    context,
                    cancellation_requested=lambda: runtime.cancellation_requested,
                )
                terminal_payload = None
            elif isinstance(outcome, RunWorkerOutcome):
                status = await self._persist_worker_outcome(
                    context,
                    outcome,
                    cancellation_requested=lambda: runtime.cancellation_requested,
                )
                terminal_payload = (
                    outcome.detached_terminal_payload()
                    if status == outcome.status
                    else None
                )
            else:
                raise TypeError("Run workers must return RunWorkerOutcome or None.")
            await self._ensure_terminal_event(
                runtime,
                status,
                payload=terminal_payload,
            )
        except asyncio.CancelledError:
            await runtime.operation_handle.begin_finalizing(
                cancellation_handled=True,
            )
            status = await self._persist_worker_terminal_status(
                context,
                status=RUN_STATUS_CANCELLED,
                error="Run cancelled by user.",
                cancellation_requested=lambda: runtime.cancellation_requested,
            )
            await self._ensure_terminal_event(runtime, status)
        except Exception as exc:
            await runtime.operation_handle.begin_finalizing(
                cancellation_handled=True,
            )
            detail = safe_exception_detail(exc)
            status = await self._persist_worker_terminal_status(
                context,
                status=RUN_STATUS_FAILED,
                error=detail,
                cancellation_requested=lambda: runtime.cancellation_requested,
            )
            await self._ensure_terminal_event(runtime, status)

    async def _persist_worker_start(
        self,
        context: RunStreamRecordContext,
        started_at_utc: str,
    ) -> str:
        def start(latest: dict[str, Any]) -> None:
            if str(latest.get("status") or "") != RUN_STATUS_QUEUED:
                return
            latest.update(
                status=RUN_STATUS_RUNNING,
                started_at_utc=started_at_utc,
            )

        record = await run_thread_to_completion(
            mutate_run_stream_record,
            context,
            start,
        )
        return str(record.get("status") or "unknown")

    async def _persist_worker_completion(
        self,
        context: RunStreamRecordContext,
        *,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> str:
        def complete(latest: dict[str, Any]) -> None:
            current_status = str(latest.get("status") or "")
            if run_status_is_terminal(current_status):
                return
            completed_at_utc = utc_now_iso()
            if current_status == RUN_STATUS_CANCELLING or (
                cancellation_requested is not None and cancellation_requested()
            ):
                latest.update(
                    status=RUN_STATUS_CANCELLED,
                    completed_at_utc=completed_at_utc,
                    error="Run cancelled by user.",
                )
                return
            error = latest.get("error")
            if error is not None:
                error = redact_sensitive_text(error)
            latest.update(
                status=RUN_STATUS_COMPLETED,
                completed_at_utc=completed_at_utc,
                error=error,
            )

        record = await run_thread_to_completion(
            mutate_run_stream_record,
            context,
            complete,
        )
        return str(record.get("status") or "unknown")

    async def _persist_worker_outcome(
        self,
        context: RunStreamRecordContext,
        outcome: RunWorkerOutcome,
        *,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> str:
        result_payload = outcome.detached_result_payload()
        correction_sequence = outcome.detached_correction_sequence()

        def commit_outcome(latest: dict[str, Any]) -> None:
            current_status = str(latest.get("status") or "")
            if run_status_is_terminal(current_status):
                return
            resolved_status = outcome.status
            resolved_error = outcome.error
            if current_status == RUN_STATUS_CANCELLING or (
                cancellation_requested is not None and cancellation_requested()
            ):
                resolved_status = RUN_STATUS_CANCELLED
                resolved_error = "Run cancelled by user."
            completed_at_utc = utc_now_iso()
            terminal_values: dict[str, Any] = {
                "status": resolved_status,
                "completed_at_utc": completed_at_utc,
                "error": (
                    redact_sensitive_text(resolved_error)
                    if resolved_error is not None
                    else None
                ),
            }
            if correction_sequence is not None:
                terminal_values["correction_sequence"] = redact_persisted_value(
                    deepcopy(correction_sequence)
                )
            if result_payload is not None:
                terminal_values["result"] = summarize_run_record(
                    {
                        **latest,
                        **terminal_values,
                        "result": result_payload,
                    }
                )
            latest.update(terminal_values)

        record = await run_thread_to_completion(
            mutate_run_stream_record,
            context,
            commit_outcome,
        )
        return str(record.get("status") or outcome.status)

    async def _persist_worker_terminal_status(
        self,
        context: RunStreamRecordContext,
        *,
        status: str,
        error: str,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> str:
        safe_error = redact_sensitive_text(error)

        def terminalize(latest: dict[str, Any]) -> None:
            current_status = str(latest.get("status") or "")
            if run_status_is_terminal(current_status):
                return
            resolved_status = status
            resolved_error = safe_error
            if (
                current_status == RUN_STATUS_CANCELLING
                or (
                    cancellation_requested is not None
                    and cancellation_requested()
                )
            ) and status != RUN_STATUS_CANCELLED:
                resolved_status = RUN_STATUS_CANCELLED
                resolved_error = "Run cancelled by user."
            latest.update(
                status=resolved_status,
                completed_at_utc=utc_now_iso(),
                error=resolved_error,
            )

        record = await run_thread_to_completion(
            mutate_run_stream_record,
            context,
            terminalize,
        )
        return str(record.get("status") or status)

    async def _ensure_terminal_event(
        self,
        runtime: _RunRuntime,
        status: str,
        *,
        payload: dict[str, Any] | None = None,
        allow_detached: bool = False,
    ) -> None:
        event_type = _TERMINAL_EVENT_FOR_STATUS.get(status)
        if event_type is None:
            return
        async with runtime.publication_lock:
            async with self._lock:
                current = self._runs.get(runtime.context.job_id)
                if current is not runtime and (
                    not allow_detached or current is not None
                ):
                    return
                if runtime.terminal_event_type is not None:
                    return
                if runtime.terminal_status is None:
                    runtime.terminal_status = status
                    runtime.terminal_event_payload = deepcopy(
                        payload
                        if payload is not None
                        else self._default_terminal_payload(runtime, status)
                    )
                retained_status = runtime.terminal_status
                event_type = _TERMINAL_EVENT_FOR_STATUS.get(retained_status)
                retained_payload = deepcopy(runtime.terminal_event_payload or {})
                pending_record = deepcopy(runtime.pending_terminal_record)
                if event_type is None:
                    return
            cancellation: asyncio.CancelledError | None = None
            record = pending_record
            if record is None:
                append_task = asyncio.create_task(
                    asyncio.to_thread(
                        append_trace_event,
                        runtime.context.trace_path,
                        event=event_type,
                        payload=retained_payload,
                    ),
                    name=f"run-terminal-append:{runtime.context.job_id}",
                )
                try:
                    record = await asyncio.shield(append_task)
                except asyncio.CancelledError as exc:
                    cancellation = exc
                    try:
                        record = await finish_shielded_task(append_task)
                    except BaseException:
                        # The worker's cancellation handler will retry terminal
                        # publication from the canonical persisted status.
                        pass
            if record is not None:
                async with self._lock:
                    if (
                        self._runs.get(runtime.context.job_id) is runtime
                        or allow_detached
                    ):
                        runtime.pending_terminal_record = deepcopy(record)
                        self._publish_record_locked(runtime, record)
                        runtime.pending_terminal_record = None
            if cancellation is not None:
                raise cancellation

    @staticmethod
    def _default_terminal_payload(
        runtime: _RunRuntime,
        status: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": runtime.context.job_id,
            "status": status,
        }
        if runtime.context.run_record.get("error"):
            payload["detail"] = redact_sensitive_text(
                runtime.context.run_record["error"]
            )
        return payload

    def _publish_record_locked(
        self,
        runtime: _RunRuntime,
        record: dict[str, Any],
    ) -> RunEventEnvelope:
        envelope = self._envelope(runtime, record)
        expected = runtime.last_published_sequence + 1
        if envelope.sequence != expected:
            raise TraceSequenceError(
                f"Run {runtime.context.job_id!r} event sequence is {envelope.sequence}; expected {expected}."
            )
        runtime.last_published_sequence = envelope.sequence
        if envelope.type in TERMINAL_RUN_EVENT_TYPES:
            runtime.terminal_event_type = envelope.type
        overflowed: list[int] = []
        for subscription_id, subscription in runtime.subscribers.items():
            if not subscription._enqueue(envelope):
                subscription._force_close("queue-overflow")
                overflowed.append(subscription_id)
        for subscription_id in overflowed:
            runtime.subscribers.pop(subscription_id, None)
        return envelope

    async def _load_trace_records(
        self,
        trace_path: Path,
        *,
        after: int,
        through: int | None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        cursor = after
        read_cursor: TraceReadCursor | None = None
        while through is None or cursor < through:
            page = await asyncio.to_thread(
                self._trace_page_loader,
                trace_path,
                after=cursor,
                limit=DEFAULT_TRACE_PAGE_LIMIT,
                cursor=read_cursor,
            )
            page_records = [
                record
                for record in page.records
                if through is None or int(record["sequence"]) <= through
            ]
            records.extend(page_records)
            if page_records:
                cursor = int(page_records[-1]["sequence"])
                read_cursor = TraceReadCursor(
                    sequence=page.next_after,
                    byte_offset=page.next_byte_offset,
                )
            if not page.has_more or not page_records or (through is not None and cursor >= through):
                break
        return records

    def _envelope(self, runtime: _RunRuntime, record: dict[str, Any]) -> RunEventEnvelope:
        return RunEventEnvelope.from_trace_record(
            run_id=runtime.context.job_id,
            session_id=str(runtime.context.prepared_run.session_id or "").strip() or None,
            record=record,
        )

    def _runtime(self, run_id: str) -> _RunRuntime:
        runtime = self._runs.get(run_id)
        if runtime is None:
            raise RunNotFoundError(run_id)
        return runtime

    def _schedule_task_cleanup(self, run_id: str, task: asyncio.Task[None]) -> None:
        current = self._cleanup_tasks.get(run_id)
        if current is not None and not current.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        cleanup = loop.create_task(
            self._handle_task_done(run_id, task),
            name=f"run-cleanup:{run_id}",
        )
        self._cleanup_tasks[run_id] = cleanup
        cleanup.add_done_callback(
            lambda finished, completed_run_id=run_id: self._cleanup_task_done(
                completed_run_id,
                finished,
            )
        )

    async def _handle_task_done(self, run_id: str, task: asyncio.Task[None]) -> None:
        async with self._lock:
            runtime = self._runs.get(run_id)
            if runtime is None or runtime.task is not task or not task.done():
                return

        task_error: BaseException | None = None
        if not task.cancelled():
            try:
                task_error = task.exception()
            except asyncio.CancelledError:
                task_error = None

        last_error: Exception | None = None
        for attempt, delay in enumerate(self._cleanup_retry_delays, start=1):
            deadline = self._shutdown_deadline
            if deadline is not None and deadline.expired:
                return
            if delay:
                if deadline is not None:
                    remaining = deadline.remaining()
                    if remaining <= 0:
                        return
                    await asyncio.sleep(min(delay, remaining))
                    if deadline.expired:
                        return
                else:
                    await asyncio.sleep(delay)
                deadline = self._shutdown_deadline
                if deadline is not None and deadline.expired:
                    return
            try:
                await self._repair_terminal_state(
                    runtime,
                    task,
                    task_error=task_error,
                )
                await self._evict_repaired_runtime(runtime, task)
                return
            except Exception as error:
                last_error = error
                LOGGER.error(
                    "Terminal cleanup attempt %d/%d failed for run %s (%s).",
                    attempt,
                    len(self._cleanup_retry_delays),
                    run_id,
                    type(error).__name__,
                )

        assert last_error is not None
        await self._retain_degraded_run(
            runtime,
            task,
            attempts=len(self._cleanup_retry_delays),
            last_error=last_error,
        )

    async def _repair_terminal_state(
        self,
        runtime: _RunRuntime,
        task: asyncio.Task[None],
        *,
        task_error: BaseException | None,
        allow_detached: bool = False,
    ) -> None:
        def terminalize_if_needed(latest: dict[str, Any]) -> None:
            current_status = str(latest.get("status") or "unknown")
            if run_status_is_terminal(current_status):
                return
            if (
                task.cancelled()
                or runtime.cancellation_requested
                or current_status == RUN_STATUS_CANCELLING
            ):
                status = RUN_STATUS_CANCELLED
                error = "Run cancelled by user."
            elif task_error is not None:
                status = RUN_STATUS_FAILED
                error = safe_exception_detail(task_error)
            else:
                status = RUN_STATUS_COMPLETED
                error = latest.get("error")
                if error is not None:
                    error = redact_sensitive_text(error)
            latest.update(
                status=status,
                completed_at_utc=utc_now_iso(),
                error=error,
            )

        record = await asyncio.to_thread(
            mutate_run_stream_record,
            runtime.context,
            terminalize_if_needed,
        )
        status = str(record.get("status") or "unknown")
        await self._ensure_terminal_event(
            runtime,
            status,
            allow_detached=allow_detached,
        )
        if runtime.terminal_event_type is None:
            raise RunCoordinatorError(
                f"Run {runtime.context.job_id!r} has no terminal event after repair."
            )

    async def _evict_repaired_runtime(
        self,
        runtime: _RunRuntime,
        task: asyncio.Task[None],
    ) -> None:
        run_id = runtime.context.job_id
        # Terminal record and terminal trace commit are synchronized and published.
        # Remove every active-only authority in one critical section, while
        # leaving existing subscription objects and their queued terminal
        # envelope untouched.
        evicted = False
        async with self._lock:
            current = self._runs.get(run_id)
            if current is not runtime or current.task is not task:
                return
            if not run_status_is_terminal(str(runtime.context.run_record.get("status") or "")):
                return
            if runtime.terminal_event_type is None:
                return
            self._runs.pop(run_id, None)
            active = self._active_runs.get(run_id)
            if active is not None and active.task is task:
                self._active_runs.pop(run_id, None)
            evicted = True
        if evicted:
            await runtime.operation_handle.finish()

    async def _retain_degraded_run(
        self,
        runtime: _RunRuntime,
        task: asyncio.Task[None],
        *,
        attempts: int,
        last_error: Exception,
    ) -> None:
        run_id = runtime.context.job_id
        retained = False
        async with self._lock:
            current = self._runs.get(run_id)
            if current is not runtime or current.task is not task or not task.done():
                return
            self._runs.pop(run_id, None)
            active = self._active_runs.get(run_id)
            if active is not None and active.task is task:
                self._active_runs.pop(run_id, None)
            for subscription in runtime.subscribers.values():
                subscription._force_close("terminal-persistence-failed")
            runtime.subscribers.clear()
            self._degraded_runs[run_id] = _DegradedRun(
                runtime=runtime,
                task=task,
                attempts=attempts,
                detected_at_utc=utc_now_iso(),
                last_error_type=type(last_error).__name__,
            )
            retained = True
        if retained:
            await runtime.operation_handle.finish()

    async def _retry_degraded_during_shutdown(
        self,
        deadline: ShutdownDeadline,
    ) -> None:
        async with self._lock:
            entries = tuple(self._degraded_runs.items())
        for run_id, entry in entries:
            if deadline.expired:
                return
            task_error: BaseException | None = None
            if not entry.task.cancelled():
                try:
                    task_error = entry.task.exception()
                except asyncio.CancelledError:
                    task_error = None
            repair = asyncio.create_task(
                self._repair_terminal_state(
                    entry.runtime,
                    entry.task,
                    task_error=task_error,
                    allow_detached=True,
                ),
                name=f"run-shutdown-degraded-repair:{run_id}",
            )
            done, pending = await deadline.wait((repair,))
            if pending:
                repair.cancel()
                repair.add_done_callback(consume_task_result)
                return
            try:
                repair.result()
            except Exception as error:
                LOGGER.error(
                    "Shutdown terminal repair failed for run %s (%s).",
                    run_id,
                    type(error).__name__,
                )
                continue
            async with self._lock:
                if self._degraded_runs.get(run_id) is entry:
                    self._degraded_runs.pop(run_id, None)

    def _cleanup_task_done(self, run_id: str, task: asyncio.Task[Any]) -> None:
        if self._cleanup_tasks.get(run_id) is task:
            self._cleanup_tasks.pop(run_id, None)
        if task.cancelled():
            return
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error is not None:
            LOGGER.critical(
                "Terminal cleanup crashed unexpectedly for run %s (%s).",
                run_id,
                type(error).__name__,
            )

__all__ = [
    "CancellationResult",
    "RunAdmissionPausedError",
    "RunCoordinator",
    "RunCoordinatorClosedError",
    "RunCoordinatorError",
    "RunCreation",
    "RunNotFoundError",
    "RunTerminalEventError",
    "RunSubscription",
    "SessionRunConflictError",
    "ShutdownResult",
    "SubscriptionDisconnectedError",
    "TraceSequenceError",
]
