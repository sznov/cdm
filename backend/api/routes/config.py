from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from backend.api.context import AppContext
from backend.services.config_management import (
    app_config_payload,
    correction_templates_payload,
    harness_payload,
    harnesses_payload,
)


def create_router(context: AppContext) -> APIRouter:
    router = APIRouter()

    @router.get("/")
    async def index() -> FileResponse:
        return FileResponse(
            context.static_dir / "index.html",
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/api/config")
    def get_config(request: Request) -> dict[str, Any]:
        startup_report = getattr(request.app.state, "startup_maintenance", {})
        startup_recovery = (
            startup_report.get("startup_recovery")
            if isinstance(startup_report, dict)
            else None
        )
        return app_config_payload(
            context.provider_catalogs,
            startup_recovery=startup_recovery,
        )

    @router.post("/api/providers/{provider_id}/models/refresh")
    async def refresh_provider_model_list(provider_id: str, force: bool = False) -> dict[str, Any]:
        return await context.provider_catalogs.refresh(provider_id, force=force)

    @router.get("/api/providers/{provider_id}/models")
    def get_provider_model_list(provider_id: str) -> dict[str, Any]:
        return context.provider_catalogs.catalog_payload(provider_id)

    @router.get("/api/health")
    async def get_health() -> dict[str, Any]:
        coordinator = context.coordinator
        coordinator_health = (
            await coordinator.health_snapshot()
            if coordinator is not None
            else {
                "status": "unavailable",
                "admission": "closed",
                "admission_generation": None,
                "admission_expires_at_utc": None,
                "operation_counts": {
                    "total": 0,
                    "provider_backed": 0,
                    "draining": 0,
                },
                "degraded_count": 0,
                "degraded_runs": [],
            }
        )
        return {
            "ok": True,
            "app": "Conceptual Model Generator",
            "coordinator": coordinator_health,
        }

    @router.get("/api/correction-templates")
    async def list_correction_templates() -> dict[str, Any]:
        return correction_templates_payload()

    @router.get("/api/harnesses")
    async def list_harnesses() -> dict[str, Any]:
        return harnesses_payload()

    @router.get("/api/harnesses/{harness_id}")
    async def get_harness(harness_id: str) -> dict[str, Any]:
        return harness_payload(harness_id)

    return router

