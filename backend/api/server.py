from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.context import AppContext, default_context, isolated_context
from backend.api.settings import BASE_DIR, DB_DIR
from backend.services.provider_model_refresh import ProviderCatalogCoordinator
from backend.services.run_operation_registry import (
    RunOperationConflictError,
    RunOperationRegistry,
    RunOperationRegistryClosedError,
)
from backend.services.shutdown_deadline import ShutdownDeadline, consume_task_result
from core.config_safety import redact_sensitive_text


_HASHED_ASSET_NAME = re.compile(r"^[^/]+-[A-Z0-9]{8}\.[A-Za-z0-9.]+$")
_DEFAULT_APPLICATION_SHUTDOWN_SECONDS = 5.0
LOGGER = logging.getLogger(__name__)


async def _sanitized_request_validation_error(
    _request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    """Preserve useful 422 locations without reflecting rejected secret input."""

    detail = [
        {
            "type": item.get("type", "value_error"),
            "loc": item.get("loc", ()),
            "msg": redact_sensitive_text(item.get("msg", "Invalid request value.")),
        }
        for item in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


def _manifest_string_values(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, dict):
        values: list[str] = []
        for nested in value.values():
            nested_values = _manifest_string_values(nested)
            if nested_values is None:
                return None
            values.extend(nested_values)
        return tuple(values)
    return None


def _normalized_static_asset_path(value: str) -> str | None:
    candidate = value.replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
    if candidate.startswith("/static/"):
        candidate = candidate.removeprefix("/static/")
    elif candidate.startswith("static/"):
        candidate = candidate.removeprefix("static/")
    else:
        candidate = candidate.lstrip("/")
    path = PurePosixPath(candidate)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "assets":
        return None
    return path.as_posix()


def _production_asset_paths(static_dir: Path) -> frozenset[str]:
    manifest_path = static_dir / "asset-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return frozenset()
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        return frozenset()
    assets = manifest.get("assets")
    entrypoints = manifest.get("entrypoints")
    chunks = manifest.get("chunks")
    if (
        not isinstance(assets, list)
        or not isinstance(entrypoints, dict)
        or not isinstance(chunks, dict)
    ):
        return frozenset()
    paths: set[str] = set()
    for value in assets:
        if not isinstance(value, str):
            return frozenset()
        normalized = _normalized_static_asset_path(value)
        if normalized is None or not _HASHED_ASSET_NAME.fullmatch(PurePosixPath(normalized).name):
            return frozenset()
        if not (static_dir / PurePosixPath(normalized)).is_file():
            return frozenset()
        paths.add(normalized)
    if len(paths) != len(assets):
        return frozenset()

    manifest_references = _manifest_string_values(
        {"entrypoints": entrypoints, "chunks": chunks}
    )
    if manifest_references is None:
        return frozenset()
    referenced_paths: set[str] = set()
    for value in manifest_references:
        normalized = _normalized_static_asset_path(value)
        if normalized is None:
            return frozenset()
        referenced_paths.add(normalized)
    if not referenced_paths or not referenced_paths <= paths:
        return frozenset()
    return frozenset(paths)


class CacheControlledStaticFiles(StaticFiles):
    def __init__(self, *, directory: Path) -> None:
        super().__init__(directory=directory)
        self._immutable_asset_paths = _production_asset_paths(directory)

    async def get_response(self, path: str, scope: dict[str, Any]):
        response = await super().get_response(path, scope)
        normalized = _normalized_static_asset_path(path)
        if normalized is not None and normalized in self._immutable_asset_paths:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-store"
        return response


def _app_lifespan(context: AppContext):
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        from core.build_provenance import current_build_identity
        from backend.persistence.startup import maintain_application_records

        try:
            # Source-mode identity requires a deterministic tree scan. Warm the
            # process cache off the event loop so the first detached POST remains
            # a fast reservation operation; packaged identities are cheap reads.
            await asyncio.to_thread(current_build_identity)
            _app.state.startup_maintenance = await asyncio.to_thread(
                maintain_application_records,
                context.runs_dir,
                context.sessions_dir,
            )
            if context.base_dir == BASE_DIR:
                context.provider_catalogs.start_background_refreshes()
            if context.coordinator is not None:
                startup = getattr(context.coordinator, "startup", None)
                if startup is not None:
                    await startup()
            yield
        finally:
            coordinator_timeout = getattr(
                context.coordinator,
                "shutdown_timeout",
                _DEFAULT_APPLICATION_SHUTDOWN_SECONDS,
            )
            deadline = ShutdownDeadline.after(coordinator_timeout)
            await context.operation_registry.begin_shutdown()
            request_catalog_shutdown = getattr(
                context.provider_catalogs,
                "request_shutdown",
                None,
            )
            if request_catalog_shutdown is not None:
                request_catalog_shutdown()

            shutdown_tasks: list[asyncio.Task[Any]] = [
                asyncio.create_task(
                    context.operation_registry.shutdown(deadline, initiate=False),
                    name="application-operation-shutdown",
                ),
                asyncio.create_task(
                    context.provider_catalogs.shutdown(deadline=deadline),
                    name="application-provider-shutdown",
                ),
            ]
            if context.coordinator is not None:
                shutdown = getattr(context.coordinator, "shutdown", None)
                if shutdown is not None:
                    shutdown_tasks.append(
                        asyncio.create_task(
                            shutdown(deadline=deadline),
                            name="application-run-shutdown",
                        )
                    )
            completed, pending = await deadline.wait(shutdown_tasks)
            errors: list[BaseException] = []
            for task in completed:
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except BaseException as error:
                    errors.append(error)
            for task in pending:
                task.cancel()
                task.add_done_callback(consume_task_result)
            _app.state.shutdown_unfinished = tuple(
                sorted(task.get_name() for task in pending)
            )
            if pending:
                LOGGER.warning(
                    "Application shutdown deadline expired with %d unfinished owner(s).",
                    len(pending),
                )
            if errors:
                raise errors[0]

    return lifespan


def create_app(
    base_dir: Path | None = None,
    *,
    static_dir: Path | None = None,
    provider_catalogs: ProviderCatalogCoordinator | None = None,
    coordinator: Any | None = None,
    active_runs: dict[str, Any] | None = None,
    operation_registry: RunOperationRegistry | None = None,
) -> FastAPI:
    if active_runs is None and coordinator is not None:
        coordinator_active_runs = getattr(coordinator, "active_runs", None)
        if coordinator_active_runs is not None:
            active_runs = coordinator_active_runs
    if operation_registry is None and coordinator is not None:
        coordinator_operation_registry = getattr(coordinator, "operation_registry", None)
        if coordinator_operation_registry is not None:
            operation_registry = coordinator_operation_registry
    if operation_registry is None:
        operation_registry = RunOperationRegistry()
    resolved_base_dir = BASE_DIR if base_dir is None else Path(base_dir).resolve()
    is_default_application = resolved_base_dir == BASE_DIR
    if provider_catalogs is None:
        providers_dir = (
            DB_DIR / "providers"
            if is_default_application
            else resolved_base_dir / "__db__" / "providers"
        )
        provider_catalogs = ProviderCatalogCoordinator(providers_dir)
    if is_default_application:
        context = default_context(
            provider_catalogs=provider_catalogs,
            active_runs=active_runs,
            operation_registry=operation_registry,
            coordinator=coordinator,
        )
        if static_dir is not None:
            context = replace(context, static_dir=Path(static_dir).resolve())
    else:
        context = isolated_context(
            resolved_base_dir,
            provider_catalogs=provider_catalogs,
            static_dir=static_dir,
            active_runs=active_runs,
            operation_registry=operation_registry,
            coordinator=coordinator,
        )

    if context.coordinator is None:
        from backend.services.run_coordinator import RunCoordinator

        context = replace(
            context,
            coordinator=RunCoordinator(
                runs_dir=context.runs_dir,
                sessions_dir=context.sessions_dir,
                active_runs=context.active_runs,
                operation_registry=context.operation_registry,
            ),
        )

    web_app = FastAPI(title="Conceptual Model Generator", lifespan=_app_lifespan(context))
    web_app.add_exception_handler(
        RequestValidationError,
        _sanitized_request_validation_error,
    )
    web_app.add_exception_handler(
        RunOperationConflictError,
        lambda _request, error: JSONResponse(
            status_code=409,
            content={"detail": redact_sensitive_text(str(error))},
        ),
    )
    web_app.add_exception_handler(
        RunOperationRegistryClosedError,
        lambda _request, error: JSONResponse(
            status_code=503,
            content={"detail": redact_sensitive_text(str(error))},
        ),
    )
    web_app.state.app_context = context
    web_app.mount("/static", CacheControlledStaticFiles(directory=context.static_dir), name="static")

    from backend.api.routes import config, corrections, decisions, runs, sessions

    for route_module in (config, sessions, runs, decisions, corrections):
        web_app.include_router(route_module.create_router(context))
    return web_app


app = create_app()


__all__ = [
    "app",
    "create_app",
]

