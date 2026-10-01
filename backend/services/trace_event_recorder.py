from __future__ import annotations

import asyncio
import inspect
import json
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from backend.persistence.common import utc_now_iso
from backend.persistence.run_path_references import normalize_web_run_path_references
from backend.persistence.run_trace import TraceDurability, append_trace_event
from backend.services.post_run_stream_control import PostRunStreamControl


MAX_POST_RUN_QUEUE_ITEMS = 256
MAX_POST_RUN_PENDING_BYTES = 8 * 1024 * 1024
MAX_POST_RUN_SINGLE_EVENT_BYTES = 8 * 1024 * 1024
POST_RUN_DELTA_FLUSH_BYTES = 4 * 1024
POST_RUN_DELTA_FLUSH_INTERVAL_SECONDS = 0.05

AsyncEventSink = Callable[
    [str, dict[str, Any]],
    Awaitable[None] | None,
]


class AsyncEventEmitter(Protocol):
    async def __call__(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        durability: TraceDurability = "buffered",
    ) -> None: ...


class PostRunEventError(RuntimeError):
    """Base error for bounded post-run trace publication."""


class PostRunEventTooLargeError(PostRunEventError):
    """Raised when one semantic event exceeds the closed byte budget."""


class PostRunEventWriterError(PostRunEventError):
    """Raised when the authoritative trace writer fails."""


@dataclass(slots=True)
class _QueuedEvent:
    event: str
    payload: dict[str, Any]
    timestamp_utc: str
    durability: TraceDurability
    byte_size: int
    completion: asyncio.Future[dict[str, Any]]


@dataclass(slots=True)
class _PendingDelta:
    event: str
    payload: dict[str, Any]
    delta: str
    byte_size: int
    durability: TraceDurability


class TraceEventRecorder:
    """Bounded asynchronous trace writer for request-owned post-run work.

    The recorder retains only sequence-range metadata. Persisted JSONL remains
    the event authority, and the optional SSE sink is delivery-only.
    """

    def __init__(
        self,
        *,
        trace_path: Path,
        event_sink: AsyncEventSink | None = None,
        stream_control: PostRunStreamControl | None = None,
        max_queue_items: int = MAX_POST_RUN_QUEUE_ITEMS,
        max_pending_bytes: int = MAX_POST_RUN_PENDING_BYTES,
        max_single_event_bytes: int = MAX_POST_RUN_SINGLE_EVENT_BYTES,
        delta_flush_bytes: int = POST_RUN_DELTA_FLUSH_BYTES,
        delta_flush_interval_seconds: float = POST_RUN_DELTA_FLUSH_INTERVAL_SECONDS,
    ) -> None:
        if max_queue_items < 1:
            raise ValueError("Post-run event queue capacity must be positive.")
        if max_pending_bytes < 1 or max_single_event_bytes < 1:
            raise ValueError("Post-run event byte budgets must be positive.")
        if max_single_event_bytes > max_pending_bytes:
            raise ValueError("A single event cannot exceed the pending-byte budget.")
        if delta_flush_bytes < 1 or delta_flush_interval_seconds <= 0:
            raise ValueError("Post-run delta flush limits must be positive.")
        self.trace_path = trace_path
        self.event_sink = event_sink
        self._stream_control = stream_control
        self._max_queue_items = max_queue_items
        self._max_pending_bytes = max_pending_bytes
        self._max_single_event_bytes = max_single_event_bytes
        self._delta_flush_bytes = delta_flush_bytes
        self._delta_flush_interval_seconds = delta_flush_interval_seconds
        self._condition = asyncio.Condition()
        self._delta_lock = asyncio.Lock()
        self._queue: deque[_QueuedEvent] = deque()
        self._pending_bytes = 0
        self._pending_delta: _PendingDelta | None = None
        self._delta_timer: asyncio.Task[None] | None = None
        self._writer_task: asyncio.Task[None] | None = None
        self._writer_error: BaseException | None = None
        self._timer_error: BaseException | None = None
        self._closing = False
        self._closed = False
        self._first_sequence: int | None = None
        self._last_sequence: int | None = None
        self._event_count = 0

    @property
    def first_sequence(self) -> int | None:
        return self._first_sequence

    @property
    def last_sequence(self) -> int | None:
        return self._last_sequence

    @property
    def event_count(self) -> int:
        return self._event_count

    def sequence_summary(self) -> dict[str, int | None]:
        return {
            "first_sequence": self._first_sequence,
            "last_sequence": self._last_sequence,
            "event_count": self._event_count,
        }

    async def __aenter__(self) -> TraceEventRecorder:
        self._ensure_writer()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: Any,
    ) -> None:
        await self.close()

    async def emit(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        durability: TraceDurability = "buffered",
    ) -> None:
        async with self._delta_lock:
            await self._flush_pending_delta_locked()
            await self._enqueue_and_wait(event, payload, durability=durability)

    async def emit_delta(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        delta_key: str = "delta",
        durability: TraceDurability = "buffered",
    ) -> None:
        delta = payload.get(delta_key)
        if not isinstance(delta, str) or not delta:
            return
        base_payload = {key: value for key, value in payload.items() if key != delta_key}
        async with self._delta_lock:
            pending = self._pending_delta
            if (
                pending is not None
                and (
                    pending.event != event
                    or pending.payload != base_payload
                    or pending.durability != durability
                )
            ):
                await self._flush_pending_delta_locked()
                pending = None
            delta_bytes = len(delta.encode("utf-8"))
            if pending is None:
                pending = _PendingDelta(
                    event=event,
                    payload=base_payload,
                    delta="",
                    byte_size=0,
                    durability=durability,
                )
                self._pending_delta = pending
                self._arm_delta_timer_locked()
            pending.delta += delta
            pending.byte_size += delta_bytes
            if pending.byte_size >= self._delta_flush_bytes:
                await self._flush_pending_delta_locked()

    async def flush(self) -> None:
        async with self._delta_lock:
            await self._flush_pending_delta_locked()
        await self._raise_background_error()

    async def deliver_committed_records(
        self,
        records: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    ) -> None:
        """Deliver journal-owned records without appending them a second time.

        The durable trace is authoritative. A delivery-only failure detaches
        the sink but never makes the already committed transaction appear to
        have failed.
        """

        await self.flush()
        for record in records:
            event = record.get("event")
            payload = record.get("payload")
            sequence = record.get("sequence")
            timestamp_utc = record.get("timestamp_utc")
            if (
                not isinstance(event, str)
                or not event
                or not isinstance(payload, dict)
                or isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence < 1
                or not isinstance(timestamp_utc, str)
                or not timestamp_utc
            ):
                raise PostRunEventWriterError(
                    "Committed post-run trace record is invalid."
                )
            self._record_persisted_sequence(sequence)
            await self._deliver_to_sink(
                event,
                payload,
                sequence=sequence,
                timestamp_utc=timestamp_utc,
            )

    async def close(self) -> None:
        if self._closed:
            await self._raise_background_error()
            return
        async with self._delta_lock:
            await self._flush_pending_delta_locked()
            timer = self._delta_timer
            self._delta_timer = None
            if timer is not None and timer is not asyncio.current_task():
                timer.cancel()
        async with self._condition:
            self._closing = True
            self._condition.notify_all()
        writer = self._writer_task
        if writer is not None:
            await asyncio.gather(writer, return_exceptions=True)
        self._closed = True
        await self._raise_background_error()

    async def _enqueue_and_wait(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        durability: TraceDurability,
    ) -> dict[str, Any]:
        if self._closing or self._closed:
            raise PostRunEventWriterError("Post-run event recorder is closed.")
        self._ensure_writer()
        normalized, byte_size = await asyncio.to_thread(
            self._normalize_and_measure,
            event,
            payload,
        )
        if byte_size > self._max_single_event_bytes:
            raise PostRunEventTooLargeError(
                "Post-run event exceeds the maximum serialized size."
            )
        loop = asyncio.get_running_loop()
        completion: asyncio.Future[dict[str, Any]] = loop.create_future()
        queued = _QueuedEvent(
            event=event,
            payload=normalized,
            timestamp_utc=utc_now_iso(),
            durability=durability,
            byte_size=byte_size,
            completion=completion,
        )
        async with self._condition:
            while (
                len(self._queue) >= self._max_queue_items
                or self._pending_bytes + byte_size > self._max_pending_bytes
            ):
                self._raise_writer_error_locked()
                if self._closing:
                    raise PostRunEventWriterError("Post-run event recorder is closing.")
                await self._condition.wait()
            self._raise_writer_error_locked()
            self._queue.append(queued)
            self._pending_bytes += byte_size
            self._condition.notify_all()
        return await completion

    def _normalize_and_measure(
        self,
        event: str,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
        normalized = normalize_web_run_path_references(
            payload,
            run_dir=self.trace_path.parent,
        )
        if not isinstance(normalized, dict):  # pragma: no cover - typed payload contract
            raise TypeError("Trace event payload normalization must preserve object shape.")
        byte_size = len(
            json.dumps(
                {"event": event, "payload": normalized},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        return normalized, byte_size

    async def _writer(self) -> None:
        while True:
            async with self._condition:
                while not self._queue and not self._closing:
                    await self._condition.wait()
                if not self._queue:
                    return
                queued = self._queue.popleft()
            try:
                record = await asyncio.to_thread(
                    append_trace_event,
                    self.trace_path,
                    event=queued.event,
                    payload=queued.payload,
                    timestamp_utc=queued.timestamp_utc,
                    durability=queued.durability,
                )
            except BaseException as exc:
                failure = PostRunEventWriterError(
                    "Post-run trace persistence failed."
                )
                failure.__cause__ = exc
                async with self._condition:
                    self._writer_error = failure
                    self._pending_bytes -= queued.byte_size
                    if not queued.completion.done():
                        queued.completion.set_exception(failure)
                    while self._queue:
                        pending = self._queue.popleft()
                        self._pending_bytes -= pending.byte_size
                        if not pending.completion.done():
                            pending.completion.set_exception(failure)
                    self._condition.notify_all()
                return

            sequence = int(record["sequence"])
            self._record_persisted_sequence(sequence)
            await self._deliver_to_sink(
                queued.event,
                queued.payload,
                sequence=sequence,
                timestamp_utc=str(record["timestamp_utc"]),
            )
            async with self._condition:
                self._pending_bytes -= queued.byte_size
                if not queued.completion.done():
                    queued.completion.set_result(record)
                self._condition.notify_all()

    def _record_persisted_sequence(self, sequence: int) -> None:
        if self._last_sequence is not None and sequence <= self._last_sequence:
            raise PostRunEventWriterError(
                "Post-run trace sequence did not advance monotonically."
            )
        if self._first_sequence is None:
            self._first_sequence = sequence
        self._last_sequence = sequence
        self._event_count += 1

    async def _deliver_to_sink(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        sequence: int,
        timestamp_utc: str,
    ) -> None:
        sink = self.event_sink
        if sink is None:
            return
        try:
            result = sink(
                event,
                {
                    **payload,
                    "__event_sequence": sequence,
                    "__trace_timestamp_utc": timestamp_utc,
                },
            )
            if inspect.isawaitable(result):
                await result
        except BaseException:
            self.event_sink = None
            if self._stream_control is not None:
                await self._stream_control.delivery_failed()

    async def _flush_pending_delta_locked(self) -> None:
        pending = self._pending_delta
        if pending is None:
            return
        self._pending_delta = None
        timer = self._delta_timer
        self._delta_timer = None
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()
        await self._enqueue_and_wait(
            pending.event,
            {**pending.payload, "delta": pending.delta},
            durability=pending.durability,
        )

    def _arm_delta_timer_locked(self) -> None:
        if self._delta_timer is None or self._delta_timer.done():
            self._delta_timer = asyncio.create_task(self._flush_delta_after_interval())

    async def _flush_delta_after_interval(self) -> None:
        try:
            await asyncio.sleep(self._delta_flush_interval_seconds)
            async with self._delta_lock:
                await self._flush_pending_delta_locked()
        except asyncio.CancelledError:
            return
        except BaseException as exc:
            self._timer_error = exc

    def _ensure_writer(self) -> None:
        if self._writer_task is None:
            self._writer_task = asyncio.create_task(self._writer())

    def _raise_writer_error_locked(self) -> None:
        if self._writer_error is not None:
            raise self._writer_error

    async def _raise_background_error(self) -> None:
        if self._timer_error is not None:
            raise self._timer_error
        if self._writer_error is not None:
            raise self._writer_error


__all__ = [
    "AsyncEventEmitter",
    "AsyncEventSink",
    "MAX_POST_RUN_PENDING_BYTES",
    "MAX_POST_RUN_QUEUE_ITEMS",
    "MAX_POST_RUN_SINGLE_EVENT_BYTES",
    "POST_RUN_DELTA_FLUSH_BYTES",
    "POST_RUN_DELTA_FLUSH_INTERVAL_SECONDS",
    "PostRunEventError",
    "PostRunEventTooLargeError",
    "PostRunEventWriterError",
    "TraceEventRecorder",
]
