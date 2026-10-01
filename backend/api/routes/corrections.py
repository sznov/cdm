from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.api.context import AppContext
from backend.api.models import CorrectionPatchRequest, CorrectionSequenceRequest, QuestionRequest
from backend.api.sse import streaming_response_from_event_worker
from backend.services.correction_patches import apply_freeform_correction_core
from backend.services.correction_sequences import apply_correction_sequence_core
from backend.services.questions import ask_model_question_core


def create_router(context: AppContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/runs/{job_id}/corrections")
    async def apply_freeform_correction(job_id: str, request: CorrectionPatchRequest) -> dict[str, Any]:
        return await apply_freeform_correction_core(
            job_id,
            request,
            runs_dir=context.runs_dir,
            sessions_dir=context.sessions_dir,
            active_runs=context.active_runs,
            operation_registry=context.operation_registry,
        )

    @router.post("/api/runs/{job_id}/correction-sequences")
    async def apply_correction_sequence(job_id: str, request: CorrectionSequenceRequest) -> dict[str, Any]:
        return await apply_correction_sequence_core(
            job_id,
            request,
            runs_dir=context.runs_dir,
            sessions_dir=context.sessions_dir,
            active_runs=context.active_runs,
            operation_registry=context.operation_registry,
        )

    @router.post("/api/runs/{job_id}/questions")
    async def ask_model_question(job_id: str, request: QuestionRequest) -> dict[str, Any]:
        return await ask_model_question_core(
            job_id,
            request,
            runs_dir=context.runs_dir,
            sessions_dir=context.sessions_dir,
            active_runs=context.active_runs,
            operation_registry=context.operation_registry,
        )

    @router.post("/api/runs/{job_id}/corrections/stream")
    async def stream_freeform_correction(job_id: str, request: CorrectionPatchRequest):
        return streaming_response_from_event_worker(
            lambda sink, stream_control: apply_freeform_correction_core(
                job_id,
                request,
                runs_dir=context.runs_dir,
                sessions_dir=context.sessions_dir,
                event_sink=sink,
                stream_control=stream_control,
                active_runs=context.active_runs,
                operation_registry=context.operation_registry,
            )
        )

    @router.post("/api/runs/{job_id}/questions/stream")
    async def stream_model_question(job_id: str, request: QuestionRequest):
        return streaming_response_from_event_worker(
            lambda sink, stream_control: ask_model_question_core(
                job_id,
                request,
                runs_dir=context.runs_dir,
                sessions_dir=context.sessions_dir,
                event_sink=sink,
                stream_control=stream_control,
                active_runs=context.active_runs,
                operation_registry=context.operation_registry,
            )
        )

    @router.post("/api/runs/{job_id}/correction-sequences/stream")
    async def stream_correction_sequence(job_id: str, request: CorrectionSequenceRequest):
        return streaming_response_from_event_worker(
            lambda sink, stream_control: apply_correction_sequence_core(
                job_id,
                request,
                runs_dir=context.runs_dir,
                sessions_dir=context.sessions_dir,
                event_sink=sink,
                stream_control=stream_control,
                active_runs=context.active_runs,
                operation_registry=context.operation_registry,
            )
        )

    return router
