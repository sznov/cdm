from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import httpx

from core.config_safety import (
    provider_environment_endpoint_url,
    validate_endpoint_url,
)
from core.providers.catalog_envelope import (
    ProviderCatalogEnvelope,
    live_catalog,
    read_persisted_catalog,
    write_catalog,
)
from core.providers.nvidia_nim_catalog import (
    NVIDIA_NIM_DEFAULT_BASE_URL,
    builtin_nvidia_nim_catalog,
    merge_v1_model_ids,
    parse_build_catalog_resources,
)

BUILD_MODELS_URL = "https://build.nvidia.com/models?filters=nimType%3Anim_type_preview"
BUILD_MODELS_MAX_PAGES = 12
_BUNDLED_NVIDIA_RETRIEVED_AT = datetime(2026, 6, 30, 20, 17, 32, tzinfo=timezone.utc)


def _bundled_nvidia_nim_catalog(entries: list[dict[str, Any]]) -> ProviderCatalogEnvelope:
    return ProviderCatalogEnvelope(
        provider_id="nvidia_nim",
        source="bundled",
        origin="bundled",
        retrieved_at_utc=_BUNDLED_NVIDIA_RETRIEVED_AT,
        stale=True,
        unverified=True,
        warning=(
            "Using the bundled NVIDIA NIM release snapshot; availability has not "
            "been verified against the configured endpoint."
        ),
        provenance={
            "snapshot_id": "nvidia-nim-release-20260630",
            "kind": "release_snapshot",
            "resource": "core.providers.data/nvidia_nim_catalog_seed.json",
            "authoritative": False,
        },
        models=entries,
    )


@lru_cache(maxsize=1)
def _load_bundled_nvidia_nim_catalog() -> ProviderCatalogEnvelope:
    entries: list[dict[str, Any]]
    try:
        seed_resource = resources.files("core.providers.data").joinpath("nvidia_nim_catalog_seed.json")
        payload = json.loads(seed_resource.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "provider_id" in payload:
            envelope = ProviderCatalogEnvelope.model_validate(payload)
            if envelope.provider_id != "nvidia_nim" or envelope.source != "bundled":
                raise ValueError("unexpected bundled NVIDIA catalog identity")
            return envelope
        raw_entries = payload.get("models") if isinstance(payload, dict) else payload
        entries = raw_entries if isinstance(raw_entries, list) else builtin_nvidia_nim_catalog()
    except (FileNotFoundError, ModuleNotFoundError, json.JSONDecodeError, OSError, ValueError):
        entries = builtin_nvidia_nim_catalog()
    return _bundled_nvidia_nim_catalog(entries)


def read_bundled_nvidia_nim_catalog() -> ProviderCatalogEnvelope:
    return _load_bundled_nvidia_nim_catalog().model_copy(deep=True)


def read_bundled_nvidia_nim_catalog_seed() -> list[dict[str, Any]]:
    return read_bundled_nvidia_nim_catalog().model_copy(deep=True).models


def read_nvidia_nim_catalog_envelope(path: Path) -> ProviderCatalogEnvelope:
    return read_persisted_catalog(path, provider_id="nvidia_nim") or read_bundled_nvidia_nim_catalog()


def read_nvidia_nim_catalog_cache(path: Path) -> list[dict[str, Any]]:
    return read_nvidia_nim_catalog_envelope(path).model_copy(deep=True).models


def write_nvidia_nim_catalog_cache(entries: list[dict[str, Any]], path: Path) -> None:
    write_catalog(
        path,
        live_catalog(
            "nvidia_nim",
            entries,
            provenance={
                "kind": "endpoint_discovery",
                "endpoint_class": "nvidia_nim",
            },
        ),
    )


async def discover_nvidia_nim_v1_model_ids(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[str]:
    key = (api_key or os.getenv("NVIDIA_API_KEY") or "").strip()
    if not key:
        return []
    environment_url = provider_environment_endpoint_url("nvidia_nim")
    resolved_base = (
        str(base_url).strip().rstrip("/")
        if base_url
        else environment_url or NVIDIA_NIM_DEFAULT_BASE_URL
    )
    validate_endpoint_url(
        resolved_base,
        field_name="NVIDIA NIM model-discovery endpoint",
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{resolved_base}/models", headers={"Authorization": f"Bearer {key}"})
        response.raise_for_status()
    payload = response.json()
    models = payload.get("data") if isinstance(payload, dict) else None
    result: list[str] = []
    if isinstance(models, list):
        for model in models:
            if isinstance(model, dict) and isinstance(model.get("id"), str):
                result.append(model["id"])
    return sorted(set(result))


async def refresh_nvidia_nim_catalog_from_v1(
    *,
    cache_path: Path,
    base_url: str | None = None,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    existing = read_nvidia_nim_catalog_cache(cache_path)
    model_ids = await discover_nvidia_nim_v1_model_ids(base_url=base_url, api_key=api_key)
    merged = merge_v1_model_ids(existing, model_ids)
    write_nvidia_nim_catalog_cache(merged, cache_path)
    return merged


def merge_nvidia_nim_build_entries(existing: list[dict[str, Any]], build_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {
        str(entry.get("canonical_model_id") or entry.get("id")): dict(entry)
        for entry in existing
        if entry.get("canonical_model_id") or entry.get("id")
    }
    for entry in build_entries:
        model_id = str(entry.get("canonical_model_id") or entry.get("id") or "")
        if not model_id:
            continue
        current = by_id.get(model_id)
        merged = {**(current or {}), **entry}
        for mapping_name in ("sources", "confidence", "source_last_success_at", "source_last_error"):
            current_mapping = current.get(mapping_name) if current else None
            incoming_mapping = entry.get(mapping_name)
            merged[mapping_name] = {
                **(current_mapping if isinstance(current_mapping, dict) else {}),
                **(incoming_mapping if isinstance(incoming_mapping, dict) else {}),
            }
        if current is None:
            # Build-site presence is metadata, not authenticated endpoint
            # availability. A later endpoint observation may promote it.
            merged["endpoint_available"] = False
            merged["stale"] = True
        else:
            for availability_field in (
                "endpoint_available",
                "stale",
                "last_seen_in_v1_models",
                "removed_from_source_at",
            ):
                if availability_field in current:
                    merged[availability_field] = current[availability_field]
        by_id[model_id] = merged
    return sorted(by_id.values(), key=lambda item: str(item.get("canonical_model_id") or item.get("id")).lower())


async def fetch_nvidia_nim_build_entries() -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for page in range(1, BUILD_MODELS_MAX_PAGES + 1):
            url = BUILD_MODELS_URL if page == 1 else f"{BUILD_MODELS_URL}&page={page}"
            response = await client.get(url)
            response.raise_for_status()
            page_entries = parse_build_catalog_resources(response.text)
            if page > 1 and not page_entries:
                break
            for entry in page_entries:
                model_id = str(entry.get("canonical_model_id") or entry.get("id") or "")
                if model_id:
                    by_id[model_id] = entry
    return sorted(by_id.values(), key=lambda item: str(item.get("canonical_model_id") or item.get("id")).lower())


async def refresh_nvidia_nim_catalog(
    *,
    cache_path: Path,
    base_url: str | None = None,
    api_key: str | None = None,
    include_build: bool = True,
    include_v1_models: bool = True,
) -> list[dict[str, Any]]:
    entries = read_nvidia_nim_catalog_cache(cache_path)
    if include_build:
        entries = merge_nvidia_nim_build_entries(entries, await fetch_nvidia_nim_build_entries())
    if include_v1_models:
        model_ids = await discover_nvidia_nim_v1_model_ids(base_url=base_url, api_key=api_key)
        entries = merge_v1_model_ids(entries, model_ids)
    write_nvidia_nim_catalog_cache(entries, cache_path)
    return entries


__all__ = [
    "BUILD_MODELS_MAX_PAGES",
    "BUILD_MODELS_URL",
    "discover_nvidia_nim_v1_model_ids",
    "fetch_nvidia_nim_build_entries",
    "merge_nvidia_nim_build_entries",
    "read_bundled_nvidia_nim_catalog",
    "read_bundled_nvidia_nim_catalog_seed",
    "read_nvidia_nim_catalog_envelope",
    "read_nvidia_nim_catalog_cache",
    "refresh_nvidia_nim_catalog",
    "refresh_nvidia_nim_catalog_from_v1",
    "write_nvidia_nim_catalog_cache",
]
