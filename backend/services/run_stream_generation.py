from __future__ import annotations

from typing import Any


class ActiveGenerationTracker:
    def __init__(self) -> None:
        self._active_generation: dict[str, Any] | None = None

    def track_event(self, event: str, payload: dict[str, Any]) -> None:
        if event.endswith("_generation_start") or (
            event.endswith("_start") and payload.get("agent_id") and payload.get("summary")
        ):
            self._active_generation = {
                "start_event": event,
                "agent_id": payload.get("agent_id"),
                "iteration": payload.get("iteration"),
                "batch_attempt": payload.get("batch_attempt"),
                "summary": payload.get("summary"),
                "output": "",
            }
            return
        if event.endswith("_delta") and "delta" in payload:
            if self._active_generation is None:
                self._active_generation = {
                    "start_event": event.removesuffix("_delta") + "_start",
                    "agent_id": payload.get("agent_id"),
                    "iteration": payload.get("iteration"),
                    "batch_attempt": payload.get("batch_attempt"),
                    "summary": f"Streaming continuation for {event.removesuffix('_delta')}.",
                    "output": "",
                }
            self._active_generation["output"] = f"{self._active_generation.get('output', '')}{payload.get('delta') or ''}"
            return
        if event.endswith("_generation_done") or (
            event.endswith("_done")
            and self._active_generation is not None
            and payload.get("agent_id") == self._active_generation.get("agent_id")
        ):
            self._active_generation = None

    def interrupted_payload(self) -> dict[str, Any] | None:
        if self._active_generation is None:
            return None
        partial_output = str(self._active_generation.get("output") or "")
        return {
            "agent_id": self._active_generation.get("agent_id"),
            "source_event": self._active_generation.get("start_event"),
            "iteration": self._active_generation.get("iteration"),
            "batch_attempt": self._active_generation.get("batch_attempt"),
            "summary": self._active_generation.get("summary"),
            "raw_output": partial_output,
            "partial_output": partial_output,
            "detail": "Generation interrupted by cancellation.",
        }
