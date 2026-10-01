from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.api.settings import BASE_DIR, RUNS_DIR, SESSIONS_DIR, STATIC_DIR
from backend.services.active_run_registry import ACTIVE_RUNS, ActiveRun
from backend.services.provider_model_refresh import ProviderCatalogCoordinator
from backend.services.run_operation_registry import RunOperationRegistry


@dataclass(frozen=True)
class AppContext:
    base_dir: Path
    static_dir: Path
    runs_dir: Path
    sessions_dir: Path
    active_runs: dict[str, ActiveRun]
    provider_catalogs: ProviderCatalogCoordinator
    operation_registry: RunOperationRegistry = field(default_factory=RunOperationRegistry)
    coordinator: Any | None = None


def default_context(
    *,
    provider_catalogs: ProviderCatalogCoordinator,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_registry: RunOperationRegistry | None = None,
    coordinator: Any | None = None,
) -> AppContext:
    return AppContext(
        base_dir=BASE_DIR,
        static_dir=STATIC_DIR,
        runs_dir=RUNS_DIR,
        sessions_dir=SESSIONS_DIR,
        active_runs=ACTIVE_RUNS if active_runs is None else active_runs,
        provider_catalogs=provider_catalogs,
        operation_registry=operation_registry or RunOperationRegistry(),
        coordinator=coordinator,
    )


def isolated_context(
    base_dir: Path,
    *,
    provider_catalogs: ProviderCatalogCoordinator,
    static_dir: Path | None = None,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_registry: RunOperationRegistry | None = None,
    coordinator: Any | None = None,
) -> AppContext:
    resolved_base = Path(base_dir).resolve()
    data_dir = resolved_base / "__db__"
    return AppContext(
        base_dir=resolved_base,
        static_dir=(static_dir or STATIC_DIR).resolve(),
        runs_dir=data_dir / "runs",
        sessions_dir=data_dir / "sessions",
        active_runs={} if active_runs is None else active_runs,
        provider_catalogs=provider_catalogs,
        operation_registry=operation_registry or RunOperationRegistry(),
        coordinator=coordinator,
    )


def __getattr__(name: str) -> Any:
    if name in {"ActiveRun", "ACTIVE_RUNS", "BASE_DIR", "STATIC_DIR", "RUNS_DIR", "SESSIONS_DIR"}:
        return globals()[name]
    raise AttributeError(name)


__all__ = ["AppContext", "default_context", "isolated_context"]
