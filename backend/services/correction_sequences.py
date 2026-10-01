from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.models import CorrectionPatchRequest, CorrectionSequenceRequest
from backend.api.settings import RUN_RECORD_FILENAME, RUN_TRACE_FILENAME
from backend.persistence.run_paths import safe_run_dir
from backend.services.active_run_registry import ActiveRun, run_is_active
from backend.services.correction_events import CorrectionEventRecorder
from backend.services.correction_patches import apply_freeform_correction_core
from backend.services.correction_templates import correction_template_by_id
from backend.services.run_operation_claims import claim_recorded_run_operation
from backend.services.run_operation_registry import (
    RunOperationHandle,
    RunOperationKind,
    RunOperationRegistry,
)
from backend.services.post_run_stream_control import PostRunStreamControl
from backend.services.trace_event_recorder import AsyncEventSink

async def _apply_correction_sequence_core(
    job_id: str,
    request: CorrectionSequenceRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    event_sink: AsyncEventSink | None = None,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_registry: RunOperationRegistry,
    operation_handle: RunOperationHandle | None = None,
    event_recorder: CorrectionEventRecorder,
) -> dict[str, Any]:
    template = correction_template_by_id(request.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Correction template not found.")
    steps = [step for step in template.get("steps") or [] if isinstance(step, dict)]
    if not steps:
        raise HTTPException(status_code=400, detail="Correction template has no steps.")

    run_dir = safe_run_dir(job_id, runs_dir=runs_dir)
    record_path = run_dir / RUN_RECORD_FILENAME
    if not record_path.is_file():
        raise HTTPException(status_code=404, detail="Run not found.")
    if run_is_active(job_id, active_runs):
        raise HTTPException(status_code=409, detail="Cannot apply correction patches while the run is still active.")

    emit = event_recorder.emit

    await emit(
        "correction_sequence_start",
        {
            "job_id": job_id,
            "template_id": template["id"],
            "template_name": template.get("name") or template["id"],
            "step_count": len(steps),
            "steps": steps,
            "summary": f"Running correction sequence: {template.get('name') or template['id']}.",
        },
    )

    phase_results: list[dict[str, Any]] = []
    accepted_count = 0
    changed_count = 0
    rejected_count = 0
    deferred_count = 0

    for index, step in enumerate(steps, start=1):
        message = str(step.get("message") or "").strip()
        if not message:
            continue
        step_payload = {
            "job_id": job_id,
            "template_id": template["id"],
            "template_name": template.get("name") or template["id"],
            "step_index": index,
            "step_count": len(steps),
            "step_id": step.get("id") or f"step-{index}",
            "step_name": step.get("name") or f"Step {index}",
            "message": message,
            "allowed_ops": step.get("allowed_ops"),
            "summary": f"Correction sequence step {index}/{len(steps)}: {step.get('name') or message}",
        }
        await emit("correction_sequence_step_start", step_payload)
        phase_start = event_recorder.event_count
        result = await apply_freeform_correction_core(
            job_id,
            CorrectionPatchRequest(
                message=message,
                max_operations=request.max_operations,
                allowed_ops=step.get("allowed_ops") if isinstance(step.get("allowed_ops"), list) else None,
            ),
            runs_dir=runs_dir,
            sessions_dir=sessions_dir,
            event_sink=event_sink,
            active_runs=active_runs,
            operation_registry=operation_registry,
            event_recorder=event_recorder,
        )
        phase_event_count = event_recorder.event_count - phase_start
        if (
            operation_handle is not None
            and not await operation_handle.begin_provider_phase()
        ):
            raise asyncio.CancelledError
        accepted_count += int(result.get("accepted_count") or 0)
        changed_count += int(result.get("changed_count") or 0)
        rejected_count += int(result.get("rejected_count") or 0)
        deferred_count += int(result.get("deferred_count") or 0)
        phase = {
            **step_payload,
            "accepted_count": int(result.get("accepted_count") or 0),
            "changed_count": int(result.get("changed_count") or 0),
            "rejected_count": int(result.get("rejected_count") or 0),
            "deferred_count": int(result.get("deferred_count") or 0),
            "parse_error": result.get("parse_error"),
            "error": result.get("error"),
            "event_count": phase_event_count,
        }
        phase_results.append(phase)
        await emit(
            "correction_sequence_step_done",
            {
                **phase,
                "summary": (
                    f"Correction sequence step {index}/{len(steps)} complete: "
                    f"{phase['accepted_count']} accepted/already satisfied, "
                    f"{phase['changed_count']} changed, {phase['rejected_count']} rejected."
                ),
            },
        )

    done_payload = {
        "job_id": job_id,
        "template_id": template["id"],
        "template_name": template.get("name") or template["id"],
        "phase_results": phase_results,
        "accepted_count": accepted_count,
        "changed_count": changed_count,
        "rejected_count": rejected_count,
        "deferred_count": deferred_count,
        "summary": (
            f"Correction sequence complete: {accepted_count} accepted/already satisfied, "
            f"{changed_count} changed, {rejected_count} rejected, {deferred_count} deferred."
        ),
    }
    if operation_handle is not None:
        await operation_handle.begin_finalizing()
    await emit("correction_sequence_done", done_payload, durability="commit")
    return done_payload


async def apply_correction_sequence_core(
    job_id: str,
    request: CorrectionSequenceRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    event_sink: AsyncEventSink | None = None,
    stream_control: PostRunStreamControl | None = None,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_registry: RunOperationRegistry,
) -> dict[str, Any]:
    if run_is_active(job_id, active_runs):
        raise HTTPException(
            status_code=409,
            detail="Cannot apply correction patches while the run is still active.",
        )
    async with claim_recorded_run_operation(
        job_id,
        RunOperationKind.CORRECTION_SEQUENCE,
        runs_dir=runs_dir,
        registry=operation_registry,
    ) as operation_handle:
        recorder: CorrectionEventRecorder | None = None
        try:
            if stream_control is not None:
                await stream_control.bind(operation_handle)
            run_dir = safe_run_dir(job_id, runs_dir=runs_dir)
            recorder = CorrectionEventRecorder(
                trace_path=run_dir / RUN_TRACE_FILENAME,
                event_sink=event_sink,
                stream_control=stream_control,
            )
            response = await _apply_correction_sequence_core(
                job_id,
                request,
                runs_dir=runs_dir,
                sessions_dir=sessions_dir,
                event_sink=event_sink,
                active_runs=active_runs,
                operation_registry=operation_registry,
                operation_handle=operation_handle,
                event_recorder=recorder,
            )
            return {**response, **recorder.sequence_summary()}
        except asyncio.CancelledError:
            if recorder is not None:
                await recorder.emit(
                    "correction_sequence_interrupted",
                    {
                        "job_id": job_id,
                        "interrupted": True,
                        "summary": "Correction sequence was interrupted before commit.",
                    },
                    durability="commit",
                )
            raise
        finally:
            if recorder is not None:
                await recorder.close()


__all__ = ["apply_correction_sequence_core"]
