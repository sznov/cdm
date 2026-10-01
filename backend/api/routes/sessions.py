from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.context import AppContext
from backend.api.models import SessionCreateRequest, SessionPatchRequest
from backend.services.session_lifecycle import (
    create_modeling_session,
    delete_modeling_session,
    patch_modeling_session,
)
from backend.services.session_queries import (
    get_modeling_session,
    list_session_summaries,
)
from backend.services.run_coordinator import SessionRunConflictError


def create_router(context: AppContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/sessions")
    def list_sessions() -> dict[str, Any]:
        return {
            "sessions": list_session_summaries(
                sessions_dir=context.sessions_dir,
                runs_dir=context.runs_dir,
            )
        }

    @router.post("/api/sessions")
    def create_session(request: SessionCreateRequest) -> dict[str, Any]:
        return create_modeling_session(request, sessions_dir=context.sessions_dir)

    @router.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        return get_modeling_session(
            session_id,
            sessions_dir=context.sessions_dir,
            runs_dir=context.runs_dir,
        )

    @router.patch("/api/sessions/{session_id}")
    def patch_session(session_id: str, request: SessionPatchRequest) -> dict[str, Any]:
        return patch_modeling_session(
            session_id,
            request,
            sessions_dir=context.sessions_dir,
            runs_dir=context.runs_dir,
        )

    @router.delete("/api/sessions/{session_id}")
    async def delete_session(session_id: str) -> dict[str, Any]:
        deletion = lambda: delete_modeling_session(
            session_id,
            sessions_dir=context.sessions_dir,
            runs_dir=context.runs_dir,
        )
        coordinator = context.coordinator
        if coordinator is None:
            return await asyncio.to_thread(deletion)
        try:
            return await coordinator.delete_session_when_idle(session_id, deletion)
        except SessionRunConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail="Stop the active run before deleting this session.",
            ) from exc

    return router
