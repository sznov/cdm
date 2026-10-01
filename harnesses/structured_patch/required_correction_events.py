from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from core.model_call_logger import ModelCallLogger
from core.schemas import StructuredModel
from harnesses.structured_patch.events import structured_model_event_payload
from harnesses.structured_patch.required_correction_types import CorrectionPhaseState
from harnesses.structured_patch.run_events import StructuredPatchRunEvents


@dataclass(frozen=True, slots=True)
class CorrectionTokenEmitter:
    events: StructuredPatchRunEvents
    job_id: str

    async def __call__(self, delta: str) -> None:
        if delta:
            await self.events.emit(
                "correction_patch_generation_delta",
                {"job_id": self.job_id, "agent_id": "patchOperationClerk", "delta": delta},
            )


@dataclass(frozen=True, slots=True)
class CorrectionApplicationEventEmitter:
    events: StructuredPatchRunEvents
    diagnostic_only: bool

    async def __call__(self, event: str, payload: dict[str, Any]) -> None:
        if self.diagnostic_only and event == "decision_patches":
            await self.events.emit(
                "correction_diagnostic_decision_patches",
                {
                    "agent_id": payload.get("agent_id") or "incrementalOpApplier",
                    "canonical": False,
                    "summary": payload.get("summary") or "Diagnostic correction decision update.",
                    "diagnostic_decisions": {
                        "decision_patches": deepcopy(payload.get("decision_patches") or []),
                    },
                },
            )
            return
        await self.events.emit(event, payload)


@dataclass(frozen=True, slots=True)
class CorrectionSnapshotEmitter:
    events: StructuredPatchRunEvents
    state: CorrectionPhaseState
    diagnostic_only: bool

    async def __call__(
        self,
        model: StructuredModel,
        reason: str,
        op_result: dict[str, Any] | None = None,
    ) -> None:
        if not self.diagnostic_only:
            await self.events.emit_partial_snapshot(model, reason, op_result)
            return
        self.state.diagnostic_snapshot_version += 1
        payload = {
            "agent_id": "asyncPlantumlRenderer",
            "canonical": False,
            "diagnostic_snapshot_version": self.state.diagnostic_snapshot_version,
            "summary": reason,
            "diagnostic_artifacts": structured_model_event_payload(model),
        }
        if op_result is not None:
            payload["op_result"] = op_result
        await self.events.emit("correction_diagnostic_snapshot", payload)


async def emit_new_model_call_logs(
    *,
    events: StructuredPatchRunEvents,
    logger: ModelCallLogger,
    state: CorrectionPhaseState,
) -> None:
    for record in logger.records[state.emitted_log_count :]:
        await events.emit("model_call_log", record)
    state.emitted_log_count = len(logger.records)


__all__ = [
    "CorrectionApplicationEventEmitter",
    "CorrectionSnapshotEmitter",
    "CorrectionTokenEmitter",
    "emit_new_model_call_logs",
]
