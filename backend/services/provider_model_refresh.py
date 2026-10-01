from __future__ import annotations

import asyncio
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from fastapi import HTTPException

from backend.persistence.locks import cache_lock
from backend.services import runtime_gemini_models as gemini_models
from backend.services import runtime_nvidia_nim_models as nvidia_models
from backend.services.shutdown_deadline import ShutdownDeadline, consume_task_result
from core.config_safety import (
    UnsafeConfigurationError,
    provider_environment_endpoint_url,
    safe_exception_detail,
)
from core.providers.catalog_envelope import (
    ProviderCatalogEnvelope,
    catalog_with_warning,
    live_catalog,
    write_catalog,
)
from core.providers.factory import DEFAULT_GEMINI_BASE_URL
from core.providers.nvidia_nim_catalog import (
    NVIDIA_NIM_DEFAULT_BASE_URL,
    merge_v1_model_ids,
)


MODEL_REFRESH_COOLDOWN_SECONDS = 30 * 60


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _initial_refresh_state(*, enrichment: bool = False) -> dict[str, Any]:
    state: dict[str, Any] = {
        "status": "idle",
        "last_started_at": None,
        "last_completed_at": None,
        "last_error": None,
        "configuration_error": None,
        "model_count": None,
        "visible_model_count": None,
        "last_success_at": None,
        "next_allowed_at": None,
    }
    if enrichment:
        state["enrichment"] = {
            "status": "idle",
            "started_at": None,
            "completed_at": None,
            "error": None,
        }
    return state


class ProviderCatalogCoordinator:
    """Own provider catalog state and tasks for exactly one application data directory."""

    def __init__(self, providers_dir: Path) -> None:
        self.providers_dir = Path(providers_dir).resolve()
        self.gemini_cache_path = (
            self.providers_dir / gemini_models.GEMINI_MODELS_CACHE_FILENAME
        )
        self.nvidia_cache_path = (
            self.providers_dir / nvidia_models.NVIDIA_NIM_CATALOG_CACHE_FILENAME
        )
        self._states = {
            "gemini": _initial_refresh_state(),
            "nvidia_nim": _initial_refresh_state(enrichment=True),
        }
        self._state_lock = RLock()
        self._refresh_tasks: dict[str, asyncio.Task[ProviderCatalogEnvelope]] = {}
        self._nvidia_enrichment_task: asyncio.Task[None] | None = None
        self._closed = False

    def _require_provider(self, provider_id: str) -> None:
        if provider_id not in ("gemini", "nvidia_nim"):
            raise HTTPException(
                status_code=404,
                detail="Provider model refresh is not supported.",
            )

    def _raw_catalog(self, provider_id: str) -> ProviderCatalogEnvelope:
        if provider_id == "gemini":
            return gemini_models.read_gemini_model_catalog(self.gemini_cache_path)
        return nvidia_models.read_nvidia_nim_model_catalog(self.nvidia_cache_path)

    def _visible_catalog(
        self,
        provider_id: str,
        catalog: ProviderCatalogEnvelope,
        state: dict[str, Any],
    ) -> ProviderCatalogEnvelope:
        if state["status"] in {
            "configuration_error",
            "failed",
            "skipped_missing_api_key",
        }:
            catalog = catalog_with_warning(catalog, state.get("last_error"))
        if provider_id == "nvidia_nim":
            enrichment = state.get("enrichment") or {}
            if enrichment.get("status") == "failed":
                catalog = catalog_with_warning(
                    catalog,
                    "NVIDIA NIM model metadata enrichment failed: "
                    f"{enrichment.get('error') or 'unknown error'}",
                )
            catalog = nvidia_models.project_nvidia_nim_model_catalog(catalog)
        return catalog

    def _state_payload(
        self,
        provider_id: str,
        catalog: ProviderCatalogEnvelope,
        state: dict[str, Any],
    ) -> dict[str, Any]:
        model_count = len(catalog.models)
        visible_count = (
            len(nvidia_models.nvidia_nim_catalog_options(catalog))
            if provider_id == "nvidia_nim"
            else model_count
        )
        return {
            **state,
            "api_key_configured": bool(
                os.getenv(
                    "GEMINI_API_KEY"
                    if provider_id == "gemini"
                    else "NVIDIA_API_KEY",
                    "",
                ).strip()
            ),
            "catalog_source": catalog.source,
            "catalog_origin": catalog.origin,
            "catalog_retrieved_at_utc": catalog.detached_dict()["retrieved_at_utc"],
            "catalog_stale": catalog.stale,
            "catalog_unverified": catalog.unverified,
            "model_count": state.get("model_count")
            if state.get("model_count") is not None
            else model_count,
            "visible_model_count": state.get("visible_model_count")
            if state.get("visible_model_count") is not None
            else visible_count,
        }

    def catalog_payload(self, provider_id: str) -> dict[str, Any]:
        """Return a detached, read-only projection without starting provider I/O."""

        self._require_provider(provider_id)
        self._synchronize_configuration_state(provider_id)
        return self._catalog_payload(provider_id)

    @staticmethod
    def _effective_endpoint(provider_id: str) -> str:
        configured = provider_environment_endpoint_url(provider_id)
        if configured:
            return configured
        if provider_id == "gemini":
            return DEFAULT_GEMINI_BASE_URL
        return NVIDIA_NIM_DEFAULT_BASE_URL

    def _synchronize_configuration_state(self, provider_id: str) -> str | None:
        try:
            endpoint = self._effective_endpoint(provider_id)
        except UnsafeConfigurationError as exc:
            with self._state_lock:
                self._mark_configuration_error_locked(
                    provider_id,
                    safe_exception_detail(exc),
                )
            return None
        with self._state_lock:
            state = self._states[provider_id]
            state["configuration_error"] = None
            if state["status"] == "configuration_error":
                state.update(
                    status="idle",
                    last_error=None,
                    next_allowed_at=None,
                )
        return endpoint

    def _catalog_payload(
        self,
        provider_id: str,
        catalog: ProviderCatalogEnvelope | None = None,
        *,
        apply_state_warnings: bool = True,
    ) -> dict[str, Any]:
        with self._state_lock:
            if catalog is None:
                resolved_catalog = self._raw_catalog(provider_id)
                state_catalog = resolved_catalog
            else:
                resolved_catalog = catalog
                state_catalog = self._raw_catalog(provider_id)
            state = deepcopy(self._states[provider_id])
        visible_catalog = (
            self._visible_catalog(provider_id, resolved_catalog, state)
            if apply_state_warnings
            else (
                nvidia_models.project_nvidia_nim_model_catalog(resolved_catalog)
                if provider_id == "nvidia_nim"
                else resolved_catalog
            )
        )
        return {
            **visible_catalog.detached_dict(),
            "state": self._state_payload(provider_id, state_catalog, state),
        }

    def _refresh_allowed_locked(self, provider_id: str, *, force: bool) -> bool:
        if force:
            return True
        next_allowed = self._states[provider_id].get("next_allowed_at")
        if not next_allowed:
            return True
        try:
            parsed = datetime.fromisoformat(str(next_allowed).replace("Z", "+00:00"))
        except ValueError:
            return True
        return _utc_now() >= parsed

    def _mark_started_locked(self, provider_id: str) -> None:
        now = _utc_now()
        self._states[provider_id].update(
            {
                "status": "running",
                "last_started_at": _iso(now),
                "last_completed_at": None,
                "last_error": None,
                "configuration_error": None,
                "next_allowed_at": _iso(
                    now + timedelta(seconds=MODEL_REFRESH_COOLDOWN_SECONDS)
                ),
            }
        )

    def _mark_configuration_error_locked(
        self,
        provider_id: str,
        detail: str,
    ) -> None:
        now = _utc_now()
        catalog = self._raw_catalog(provider_id)
        visible_count = (
            len(nvidia_models.nvidia_nim_catalog_options(catalog))
            if provider_id == "nvidia_nim"
            else len(catalog.models)
        )
        self._states[provider_id].update(
            {
                "status": "configuration_error",
                "last_started_at": None,
                "last_completed_at": _iso(now),
                "last_error": detail,
                "configuration_error": detail,
                "next_allowed_at": None,
                "model_count": len(catalog.models),
                "visible_model_count": visible_count,
            }
        )

    def _mark_missing_key_locked(self, provider_id: str) -> None:
        now = _utc_now()
        environment_name = (
            "GEMINI_API_KEY" if provider_id == "gemini" else "NVIDIA_API_KEY"
        )
        catalog = self._raw_catalog(provider_id)
        visible_count = (
            len(nvidia_models.nvidia_nim_catalog_options(catalog))
            if provider_id == "nvidia_nim"
            else len(catalog.models)
        )
        self._states[provider_id].update(
            {
                "status": "skipped_missing_api_key",
                "last_started_at": _iso(now),
                "last_completed_at": _iso(now),
                "last_error": f"{environment_name} is not configured.",
                "next_allowed_at": _iso(
                    now + timedelta(seconds=MODEL_REFRESH_COOLDOWN_SECONDS)
                ),
                "model_count": len(catalog.models),
                "visible_model_count": visible_count,
            }
        )

    def _start_refresh(
        self,
        provider_id: str,
        *,
        force: bool,
    ) -> asyncio.Task[ProviderCatalogEnvelope] | None:
        self._require_provider(provider_id)
        endpoint = self._synchronize_configuration_state(provider_id)
        if endpoint is None:
            return None
        environment_name = (
            "GEMINI_API_KEY" if provider_id == "gemini" else "NVIDIA_API_KEY"
        )
        with self._state_lock:
            if self._closed:
                return None
            existing = self._refresh_tasks.get(provider_id)
            if existing is not None and not existing.done():
                return existing
            if not self._refresh_allowed_locked(provider_id, force=force):
                if self._states[provider_id]["status"] != "skipped_missing_api_key":
                    self._states[provider_id]["status"] = "using_cached_list"
                return None
            if not os.getenv(environment_name, "").strip():
                self._mark_missing_key_locked(provider_id)
                return None
            self._mark_started_locked(provider_id)
            coroutine = (
                self._run_gemini_refresh(endpoint)
                if provider_id == "gemini"
                else self._run_nvidia_refresh(endpoint)
            )
            task = asyncio.get_running_loop().create_task(coroutine)
            self._refresh_tasks[provider_id] = task
            return task

    def start_background_refreshes(self) -> None:
        """Start non-forced refreshes for the default application."""

        for provider_id in ("gemini", "nvidia_nim"):
            self._start_refresh(provider_id, force=False)

    async def refresh(self, provider_id: str, *, force: bool = False) -> dict[str, Any]:
        self._require_provider(provider_id)
        task = self._start_refresh(provider_id, force=force)
        if task is not None:
            catalog = await asyncio.shield(task)
            return self._catalog_payload(
                provider_id,
                catalog,
                apply_state_warnings=False,
            )
        return self.catalog_payload(provider_id)

    async def _run_gemini_refresh(self, endpoint: str) -> ProviderCatalogEnvelope:
        provider_id = "gemini"
        current = asyncio.current_task()
        try:
            models, warning = await gemini_models.list_gemini_models(
                cache_path=self.gemini_cache_path,
                base_url=endpoint,
                live=True,
            )
            if warning:
                raise RuntimeError(warning)
            envelope = live_catalog(
                provider_id,
                models,
                provenance={
                    "kind": "endpoint_discovery",
                    "endpoint_class": "gemini_openai_compatible",
                },
            )
            with self._state_lock:
                with cache_lock(self.gemini_cache_path):
                    write_catalog(self.gemini_cache_path, envelope)
                completed_at = _utc_now()
                self._states[provider_id].update(
                    {
                        "status": "succeeded",
                        "last_completed_at": _iso(completed_at),
                        "last_error": None,
                        "model_count": len(models),
                        "visible_model_count": len(models),
                        "last_success_at": _iso(completed_at),
                    }
                )
        except asyncio.CancelledError:
            with self._state_lock:
                self._states[provider_id]["status"] = "idle"
            raise
        except Exception as exc:  # pragma: no cover - defensive task boundary
            with self._state_lock:
                envelope = catalog_with_warning(
                    gemini_models.read_gemini_model_catalog(
                        self.gemini_cache_path
                    ),
                    "Live Gemini discovery failed; using the best available "
                    "fallback catalog.",
                )
                cached = envelope.models
                self._states[provider_id].update(
                    {
                        "status": "failed",
                        "last_completed_at": _iso(_utc_now()),
                        "last_error": (
                            f"{type(exc).__name__}: {safe_exception_detail(exc)}"
                        ),
                        "model_count": len(cached),
                        "visible_model_count": len(cached),
                    }
                )
        finally:
            with self._state_lock:
                if self._refresh_tasks.get(provider_id) is current:
                    self._refresh_tasks.pop(provider_id, None)
        return envelope

    async def _run_nvidia_refresh(self, endpoint: str) -> ProviderCatalogEnvelope:
        provider_id = "nvidia_nim"
        current = asyncio.current_task()
        try:
            observed_at = _utc_now()
            observed_marker = observed_at.isoformat().replace("+00:00", "Z")
            model_ids = await asyncio.wait_for(
                nvidia_models.discover_nvidia_nim_v1_model_ids(
                    base_url=endpoint,
                    api_key=os.getenv("NVIDIA_API_KEY", "").strip(),
                ),
                timeout=10.0,
            )
            with self._state_lock:
                with cache_lock(self.nvidia_cache_path):
                    latest = nvidia_models.read_nvidia_nim_model_catalog(
                        self.nvidia_cache_path
                    )
                    entries = merge_v1_model_ids(
                        latest.model_copy(deep=True).models,
                        model_ids,
                        observed_at=observed_marker,
                    )
                    for entry in entries:
                        if entry.get("last_seen_in_v1_models") != observed_marker:
                            entry["endpoint_available"] = False
                            entry["stale"] = True
                    envelope = live_catalog(
                        provider_id,
                        entries,
                        retrieved_at_utc=observed_at,
                        provenance={
                            "kind": "endpoint_discovery",
                            "endpoint_class": "nvidia_nim",
                            "includes_build_catalog": False,
                        },
                    )
                    write_catalog(self.nvidia_cache_path, envelope)
                completed_at = _utc_now()
                self._states[provider_id].update(
                    {
                        "status": "succeeded",
                        "last_completed_at": _iso(completed_at),
                        "last_error": None,
                        "model_count": len(entries),
                        "visible_model_count": len(
                            nvidia_models.nvidia_nim_catalog_options(envelope)
                        ),
                        "last_success_at": _iso(completed_at),
                    }
                )
        except asyncio.CancelledError:
            with self._state_lock:
                self._states[provider_id]["status"] = "idle"
            raise
        except Exception as exc:  # pragma: no cover - defensive task boundary
            with self._state_lock:
                envelope = catalog_with_warning(
                    nvidia_models.read_nvidia_nim_model_catalog(
                        self.nvidia_cache_path
                    ),
                    "Live NVIDIA NIM discovery failed; using the best available "
                    "fallback catalog.",
                )
                visible = nvidia_models.nvidia_nim_catalog_options(envelope)
                self._states[provider_id].update(
                    {
                        "status": "failed",
                        "last_completed_at": _iso(_utc_now()),
                        "last_error": (
                            f"{type(exc).__name__}: {safe_exception_detail(exc)}"
                        ),
                        "model_count": len(envelope.models),
                        "visible_model_count": len(visible),
                    }
                )
        else:
            self._start_nvidia_enrichment()
        finally:
            with self._state_lock:
                if self._refresh_tasks.get(provider_id) is current:
                    self._refresh_tasks.pop(provider_id, None)
        return envelope

    def _start_nvidia_enrichment(self) -> bool:
        with self._state_lock:
            if self._closed:
                return False
            task = self._nvidia_enrichment_task
            if task is not None and not task.done():
                return False
            self._states["nvidia_nim"]["enrichment"] = {
                "status": "running",
                "started_at": _iso(_utc_now()),
                "completed_at": None,
                "error": None,
            }
            self._nvidia_enrichment_task = asyncio.get_running_loop().create_task(
                self._run_nvidia_enrichment()
            )
            return True

    async def _run_nvidia_enrichment(self) -> None:
        current = asyncio.current_task()
        try:
            build_entries = await nvidia_models.fetch_nvidia_nim_build_entries()
            with self._state_lock:
                with cache_lock(self.nvidia_cache_path):
                    latest = nvidia_models.read_nvidia_nim_model_catalog(
                        self.nvidia_cache_path
                    )
                    if latest.origin != "live":
                        raise RuntimeError(
                            "NVIDIA NIM availability catalog is no longer live."
                        )
                    entries = nvidia_models.merge_nvidia_nim_build_entries(
                        latest.model_copy(deep=True).models,
                        build_entries,
                    )
                    provenance = {
                        **latest.model_copy(deep=True).provenance,
                        "includes_build_catalog": True,
                        "build_catalog_enriched_at_utc": _iso(_utc_now()),
                    }
                    enriched = live_catalog(
                        "nvidia_nim",
                        entries,
                        retrieved_at_utc=latest.retrieved_at_utc,
                        provenance=provenance,
                    )
                    write_catalog(self.nvidia_cache_path, enriched)
                self._states["nvidia_nim"]["enrichment"] = {
                    **deepcopy(
                        self._states["nvidia_nim"].get("enrichment") or {}
                    ),
                    "status": "succeeded",
                    "completed_at": _iso(_utc_now()),
                    "error": None,
                }
        except asyncio.CancelledError:
            with self._state_lock:
                self._states["nvidia_nim"]["enrichment"] = {
                    "status": "idle",
                    "started_at": None,
                    "completed_at": None,
                    "error": None,
                }
            raise
        except Exception as exc:  # pragma: no cover - defensive task boundary
            with self._state_lock:
                self._states["nvidia_nim"]["enrichment"] = {
                    **deepcopy(
                        self._states["nvidia_nim"].get("enrichment") or {}
                    ),
                    "status": "failed",
                    "completed_at": _iso(_utc_now()),
                    "error": (
                        f"{type(exc).__name__}: {safe_exception_detail(exc)}"
                    ),
                }
        finally:
            with self._state_lock:
                if self._nvidia_enrichment_task is current:
                    self._nvidia_enrichment_task = None

    def request_shutdown(self) -> tuple[asyncio.Task[Any], ...]:
        """Close the coordinator and synchronously cancel its owned tasks."""

        with self._state_lock:
            self._closed = True
            tasks: list[asyncio.Task[Any]] = [
                task for task in self._refresh_tasks.values() if not task.done()
            ]
            if (
                self._nvidia_enrichment_task is not None
                and not self._nvidia_enrichment_task.done()
            ):
                tasks.append(self._nvidia_enrichment_task)
        for task in tasks:
            task.cancel()
        return tuple(tasks)

    async def shutdown(
        self,
        deadline: ShutdownDeadline | None = None,
    ) -> tuple[str, ...]:
        """Cancel owned tasks and await only within the shared shutdown budget."""

        tasks = self.request_shutdown()
        pending: set[asyncio.Task[Any]] = set()
        if tasks and deadline is None:
            await asyncio.gather(*tasks, return_exceptions=True)
        elif tasks and deadline is not None:
            _done, pending = await deadline.wait(tasks)
            for task in pending:
                task.add_done_callback(consume_task_result)
        with self._state_lock:
            self._refresh_tasks = {
                provider_id: task
                for provider_id, task in self._refresh_tasks.items()
                if not task.done()
            }
            if (
                self._nvidia_enrichment_task is not None
                and self._nvidia_enrichment_task.done()
            ):
                self._nvidia_enrichment_task = None
        return tuple(sorted(task.get_name() for task in pending))


__all__ = [
    "MODEL_REFRESH_COOLDOWN_SECONDS",
    "ProviderCatalogCoordinator",
]
