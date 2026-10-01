from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.persistence.locks import cache_lock
from core.providers.catalog_envelope import ProviderCatalogEnvelope
from core.providers.nvidia_nim_catalog import nvidia_nim_model_options
from core.providers.nvidia_nim_discovery import (
    discover_nvidia_nim_v1_model_ids,
    fetch_nvidia_nim_build_entries,
    merge_nvidia_nim_build_entries,
    read_nvidia_nim_catalog_cache as read_catalog_cache,
    read_nvidia_nim_catalog_envelope as read_catalog_envelope,
    write_nvidia_nim_catalog_cache as write_catalog_cache,
)


NVIDIA_NIM_CATALOG_CACHE_FILENAME = "nvidia_nim_catalog.json"


def read_nvidia_nim_catalog_cache(path: Path) -> list[dict[str, Any]]:
    return read_catalog_cache(path)


def read_nvidia_nim_model_catalog(path: Path) -> ProviderCatalogEnvelope:
    """Read one explicit application cache, falling back to bundled release data."""

    return read_catalog_envelope(path)


def write_nvidia_nim_catalog_cache(entries: list[dict[str, Any]], path: Path) -> None:
    with cache_lock(path):
        write_catalog_cache(entries, path)


def nvidia_nim_catalog_options(catalog: ProviderCatalogEnvelope) -> list[dict[str, Any]]:
    options = nvidia_nim_model_options(
        catalog.model_copy(deep=True).models,
        endpoint_available_only=catalog.origin == "live",
    )
    if options:
        return options
    # Endpoint membership is advisory. An empty live projection must not make
    # the application unusable when bundled/build metadata is still present.
    return nvidia_nim_model_options(catalog.model_copy(deep=True).models)


def list_nvidia_nim_models(*, cache_path: Path) -> list[dict[str, Any]]:
    return nvidia_nim_catalog_options(read_nvidia_nim_model_catalog(cache_path))


def project_nvidia_nim_model_catalog(
    catalog: ProviderCatalogEnvelope,
) -> ProviderCatalogEnvelope:
    return catalog.with_models(nvidia_nim_catalog_options(catalog))


__all__ = [
    "NVIDIA_NIM_CATALOG_CACHE_FILENAME",
    "discover_nvidia_nim_v1_model_ids",
    "fetch_nvidia_nim_build_entries",
    "list_nvidia_nim_models",
    "merge_nvidia_nim_build_entries",
    "nvidia_nim_catalog_options",
    "project_nvidia_nim_model_catalog",
    "read_nvidia_nim_catalog_cache",
    "read_nvidia_nim_model_catalog",
    "write_nvidia_nim_catalog_cache",
]
