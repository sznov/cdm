from __future__ import annotations

from fastapi import APIRouter

from backend.api.context import AppContext
from backend.api.models import DecisionPatchApplyRequest
from backend.services.decision_patch_application import apply_decision_patches_core


def create_router(context: AppContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/runs/{job_id}/decision-patches/apply")
    async def apply_decision_patches(job_id: str, request: DecisionPatchApplyRequest) -> dict:
        return await apply_decision_patches_core(
            job_id,
            request,
            runs_dir=context.runs_dir,
            sessions_dir=context.sessions_dir,
            active_runs=context.active_runs,
            operation_registry=context.operation_registry,
        )

    return router
