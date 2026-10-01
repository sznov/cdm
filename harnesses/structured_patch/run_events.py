from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from harnesses.contracts import HarnessDomainEvent
from harnesses.structured_patch.checkpoints import write_one_shot_run_checkpoint
from harnesses.structured_patch.events import structured_model_event_payload
from core.schemas import StructuredModel

RunEventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class StructuredPatchRunEvents:
    def __init__(
        self,
        *,
        job_id: str,
        model_call_log_dir: Path | None,
        on_event: RunEventCallback | None,
    ) -> None:
        self.job_id = job_id
        self.model_call_log_dir = model_call_log_dir
        self.on_event = on_event
        self.diagram_version = 0

    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        event_type, detached_payload = HarnessDomainEvent.from_parts(event, payload).detached_parts()
        if self.on_event is not None:
            await self.on_event(event_type, detached_payload)

    async def checkpoint(self, stage: str, payload: dict[str, Any], summary: str) -> None:
        checkpoint_record = write_one_shot_run_checkpoint(
            self.model_call_log_dir,
            job_id=self.job_id,
            stage=stage,
            payload=payload,
        )
        if checkpoint_record is not None:
            await self.emit(
                "checkpoint_written",
                {
                    "agent_id": "runtime",
                    **checkpoint_record,
                    "summary": summary,
                },
            )

    async def emit_partial_snapshot(
        self,
        model: StructuredModel,
        reason: str,
        op_result: dict[str, Any] | None = None,
    ) -> None:
        self.diagram_version += 1
        payload = {
            "agent_id": "asyncPlantumlRenderer",
            "diagram_version": self.diagram_version,
            "summary": reason,
            **structured_model_event_payload(model),
        }
        if op_result is not None:
            payload["op_result"] = op_result
            payload["accepted"] = [{"op": op_result.get("op"), "result": op_result}]
        await self.emit("partial_model_snapshot", payload)


__all__ = ["RunEventCallback", "StructuredPatchRunEvents"]
