from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from core.config_safety import redact_sensitive_value, safe_exception_detail
from backend.services.trace_event_recorder import (
    MAX_POST_RUN_PENDING_BYTES,
    MAX_POST_RUN_QUEUE_ITEMS,
    MAX_POST_RUN_SINGLE_EVENT_BYTES,
    PostRunEventTooLargeError,
)
from backend.services.post_run_stream_control import PostRunStreamControl


POST_RUN_DELIVERY_TIMEOUT_SECONDS = 2.0
_LOGGER = logging.getLogger(__name__)


class PostRunStreamClosedError(RuntimeError):
    """Raised by a delivery-only sink after its consumer disconnects."""


class PostRunStreamDeliveryTimeoutError(PostRunStreamClosedError):
    """Raised once when a slow post-run SSE consumer exceeds its bound."""


EventSink = Callable[[str, dict[str, Any]], Awaitable[None]]
EventWorker = Callable[
    [EventSink, PostRunStreamControl],
    Awaitable[Any],
]


def format_sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def format_sse_message(payload: dict[str, Any], *, event_id: int | str | None = None) -> str:
    """Format a default SSE message, optionally with a reconnect cursor.

    Reconnectable run observation keeps the domain event name in the typed
    payload. Using the default SSE message lets one ``EventSource.onmessage``
    handler consume every current and future domain event without maintaining
    a browser-side list of named SSE event listeners.
    """

    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {json.dumps(payload, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


def sse_comment(text: str = "") -> str:
    return f": {text}\n\n"


class _BoundedSseDelivery:
    def __init__(self, *, insertion_timeout_seconds: float) -> None:
        if insertion_timeout_seconds <= 0:
            raise ValueError("Post-run delivery timeout must be positive.")
        self._condition = asyncio.Condition()
        self._items: deque[tuple[str, int]] = deque()
        self._pending_bytes = 0
        self._closed = False
        self._insertion_timeout_seconds = insertion_timeout_seconds

    async def put(self, event: str, payload: dict[str, Any]) -> None:
        message = await asyncio.to_thread(format_sse, event, payload)
        byte_size = len(message.encode("utf-8"))
        if byte_size > MAX_POST_RUN_SINGLE_EVENT_BYTES:
            raise PostRunEventTooLargeError(
                "Post-run stream event exceeds the maximum serialized size."
            )
        deadline = (
            asyncio.get_running_loop().time()
            + self._insertion_timeout_seconds
        )
        async with self._condition:
            while (
                len(self._items) >= MAX_POST_RUN_QUEUE_ITEMS
                or self._pending_bytes + byte_size > MAX_POST_RUN_PENDING_BYTES
            ):
                if self._closed:
                    raise PostRunStreamClosedError
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    self._closed = True
                    self._condition.notify_all()
                    raise PostRunStreamDeliveryTimeoutError(
                        "Post-run SSE delivery exceeded its insertion deadline."
                    )
                try:
                    await asyncio.wait_for(
                        self._condition.wait(),
                        timeout=remaining,
                    )
                except TimeoutError as exc:
                    self._closed = True
                    self._condition.notify_all()
                    raise PostRunStreamDeliveryTimeoutError(
                        "Post-run SSE delivery exceeded its insertion deadline."
                    ) from exc
            if self._closed:
                raise PostRunStreamClosedError
            self._items.append((message, byte_size))
            self._pending_bytes += byte_size
            self._condition.notify_all()

    async def get(self) -> str | None:
        async with self._condition:
            while not self._items and not self._closed:
                await self._condition.wait()
            if not self._items:
                return None
            message, byte_size = self._items.popleft()
            self._pending_bytes -= byte_size
            self._condition.notify_all()
            return message

    async def close(self, *, discard: bool = False) -> None:
        async with self._condition:
            self._closed = True
            if discard:
                self._items.clear()
                self._pending_bytes = 0
            self._condition.notify_all()


def _consume_detached_worker(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    try:
        failure = task.exception()
    except asyncio.CancelledError:
        return
    if failure is not None:
        _LOGGER.error(
            "Detached post-run stream worker failed: %s",
            safe_exception_detail(failure),
        )


def streaming_response_from_event_worker(
    worker: EventWorker,
    *,
    insertion_timeout_seconds: float = POST_RUN_DELIVERY_TIMEOUT_SECONDS,
) -> StreamingResponse:
    delivery = _BoundedSseDelivery(
        insertion_timeout_seconds=insertion_timeout_seconds,
    )
    stream_control = PostRunStreamControl()
    worker_finished = asyncio.Event()

    async def sink(event: str, payload: dict[str, Any]) -> None:
        await delivery.put(event, payload)

    async def run_worker() -> None:
        try:
            await worker(sink, stream_control)
        except asyncio.CancelledError:
            raise
        except HTTPException as exc:
            await sink("error", {"detail": redact_sensitive_value(exc.detail)})
        except Exception as exc:
            await sink("error", {"detail": safe_exception_detail(exc)})
        finally:
            worker_finished.set()
            await delivery.close()

    async def event_stream():
        task = asyncio.create_task(run_worker())
        try:
            while True:
                message = await delivery.get()
                if message is None:
                    break
                yield message
        finally:
            if not worker_finished.is_set():
                await delivery.close(discard=True)
                disposition = await stream_control.disconnect()
                if disposition.join_worker:
                    await asyncio.gather(task, return_exceptions=True)
                elif not task.done():
                    task.add_done_callback(_consume_detached_worker)
                else:
                    _consume_detached_worker(task)
            else:
                await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = [
    "EventSink",
    "EventWorker",
    "POST_RUN_DELIVERY_TIMEOUT_SECONDS",
    "PostRunStreamClosedError",
    "PostRunStreamDeliveryTimeoutError",
    "format_sse",
    "format_sse_message",
    "sse_comment",
    "streaming_response_from_event_worker",
]
