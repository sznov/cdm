from __future__ import annotations

import json
from typing import Any

from backend.services.trace_event_recorder import (
    MAX_POST_RUN_PENDING_BYTES,
    MAX_POST_RUN_SINGLE_EVENT_BYTES,
    PostRunEventTooLargeError,
    TraceEventRecorder,
)


CorrectionEventRecorder = TraceEventRecorder


class CorrectionApplicationEventBuffer:
    """Small bounded bridge for the synchronous structured-patch applier."""

    MAX_EVENTS = 512

    def __init__(self) -> None:
        self._items: list[tuple[str, dict[str, Any]]] = []
        self._pending_bytes = 0

    def emit(self, event: str, payload: dict[str, Any]) -> None:
        if len(self._items) >= self.MAX_EVENTS:
            raise RuntimeError("Correction application emitted too many semantic events.")
        byte_size = len(
            json.dumps(
                {"event": event, "payload": payload},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if (
            byte_size > MAX_POST_RUN_SINGLE_EVENT_BYTES
            or self._pending_bytes + byte_size > MAX_POST_RUN_PENDING_BYTES
        ):
            raise PostRunEventTooLargeError(
                "Correction application events exceed the bounded byte budget."
            )
        self._items.append((event, payload))
        self._pending_bytes += byte_size

    async def drain_to(self, recorder: TraceEventRecorder) -> None:
        for event, payload in self._items:
            await recorder.emit(event, payload)
        self._items.clear()
        self._pending_bytes = 0


__all__ = ["CorrectionApplicationEventBuffer", "CorrectionEventRecorder"]
