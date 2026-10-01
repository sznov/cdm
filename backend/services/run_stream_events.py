from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from backend.persistence.run_path_references import normalize_web_run_path_references
from backend.services.run_stream_generation import ActiveGenerationTracker


class RunStreamEventBus:
    def __init__(
        self,
        *,
        generation_tracker: ActiveGenerationTracker,
        event_publisher: Callable[[str, dict[str, Any]], Awaitable[None]],
        run_dir: Path,
    ) -> None:
        self._generation_tracker = generation_tracker
        self._event_publisher = event_publisher
        self._run_dir = run_dir

    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        normalized = normalize_web_run_path_references(
            payload,
            run_dir=self._run_dir,
        )
        if not isinstance(normalized, dict):  # pragma: no cover - typed payload contract
            raise TypeError("Run event payload normalization must preserve object shape.")
        self._generation_tracker.track_event(event, normalized)
        await self._event_publisher(event, normalized)

    def end(self) -> None:
        return None

    def interrupted_payload(self) -> dict[str, Any] | None:
        return self._generation_tracker.interrupted_payload()


__all__ = ["RunStreamEventBus"]
