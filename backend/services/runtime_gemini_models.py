from __future__ import annotations

import os
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

import httpx

from backend.persistence.locks import cache_lock
from core.config_safety import (
    provider_environment_endpoint_url,
    safe_exception_detail,
    validate_endpoint_url,
)
from core.providers.catalog_envelope import (
    ProviderCatalogEnvelope,
    live_catalog,
    read_persisted_catalog,
    write_catalog,
)
from core.providers.factory import DEFAULT_GEMINI_BASE_URL


GEMINI_MODELS_CACHE_FILENAME = "gemini_models.json"

_BUNDLED_GEMINI_DISPLAY_NAMES = {
    "gemma-4-31b-it": "Gemma 4 31B IT",
    "gemini-3.5-flash": "Gemini 3.5 Flash",
    "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash Lite Preview",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
}


def _emergency_bundled_catalog() -> ProviderCatalogEnvelope:
    model_ids = tuple(_BUNDLED_GEMINI_DISPLAY_NAMES)
    return ProviderCatalogEnvelope(
        provider_id="gemini",
        source="bundled",
        origin="bundled",
        retrieved_at_utc=datetime(2026, 7, 11, tzinfo=timezone.utc),
        stale=True,
        unverified=True,
        warning=(
            "Using the bundled Gemini release snapshot; availability has not been "
            "verified against the configured endpoint."
        ),
        provenance={
            "snapshot_id": "gemini-release-20260711",
            "kind": "release_snapshot",
            "authoritative": False,
        },
        models=[
            {
                "id": model_id,
                "name": _BUNDLED_GEMINI_DISPLAY_NAMES[model_id],
                "modified_at": None,
                "size": None,
                "details": None,
            }
            for model_id in model_ids
        ],
    )


def read_bundled_gemini_catalog() -> ProviderCatalogEnvelope:
    try:
        resource = resources.files("core.providers.data").joinpath("gemini_catalog_seed.json")
        envelope = ProviderCatalogEnvelope.model_validate_json(resource.read_text(encoding="utf-8"))
        if envelope.provider_id != "gemini" or envelope.source != "bundled":
            raise ValueError("unexpected bundled Gemini catalog identity")
        return envelope
    except (FileNotFoundError, ModuleNotFoundError, OSError, ValueError):
        return _emergency_bundled_catalog()


def read_gemini_model_catalog(path: Path) -> ProviderCatalogEnvelope:
    """Read one explicit application cache, falling back to bundled release data."""

    return read_persisted_catalog(path, provider_id="gemini") or read_bundled_gemini_catalog()


def read_gemini_models_cache(path: Path) -> list[dict[str, Any]]:
    return read_gemini_model_catalog(path).model_copy(deep=True).models


def write_gemini_models_cache(models: list[dict[str, Any]], path: Path) -> None:
    envelope = live_catalog(
        "gemini",
        models,
        provenance={
            "kind": "endpoint_discovery",
            "endpoint_class": "gemini_openai_compatible",
        },
    )
    with cache_lock(path):
        write_catalog(path, envelope)


def gemini_model_id(model: dict[str, Any]) -> str:
    value = str(model.get("id") or model.get("name") or "").strip()
    if value.startswith("models/"):
        value = value.removeprefix("models/")
    return value


def is_gemini_text_model(model_id: str) -> bool:
    lowered = model_id.lower()
    blocked_terms = (
        "aqa",
        "audio",
        "embedding",
        "imagen",
        "image",
        "tts",
        "veo",
        "vision",
        "whisper",
    )
    return bool(model_id) and not any(term in lowered for term in blocked_terms)


async def list_gemini_models(
    *,
    cache_path: Path,
    base_url: str | None = None,
    live: bool = False,
) -> tuple[list[dict[str, Any]], str | None]:
    """Return models for one explicit cache; perform provider I/O only when requested."""

    fallback = read_gemini_models_cache(cache_path)
    if not live:
        return fallback, None

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return fallback, "GEMINI_API_KEY is not set; showing configured fallback models."

    environment_url = provider_environment_endpoint_url("gemini")
    resolved_url = (
        str(base_url).strip().rstrip("/")
        if base_url
        else environment_url or DEFAULT_GEMINI_BASE_URL
    )
    validate_endpoint_url(resolved_url, field_name="Gemini model-discovery endpoint")
    models_url = f"{resolved_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        return (
            fallback,
            "Gemini model discovery failed; showing configured fallback models. "
            f"{safe_exception_detail(exc)}",
        )

    payload = response.json()
    models: list[dict[str, Any]] = []
    for raw_model in payload.get("data") or payload.get("models") or []:
        if not isinstance(raw_model, dict):
            continue
        model_id = gemini_model_id(raw_model)
        if not is_gemini_text_model(model_id):
            continue
        display_name = str(raw_model.get("display_name") or model_id)
        models.append(
            {
                "id": model_id,
                "name": display_name,
                "modified_at": raw_model.get("modified_at") or raw_model.get("created"),
                "size": raw_model.get("size"),
                "details": raw_model,
            }
        )
    models.sort(key=lambda item: item["id"].lower())
    if models:
        return models, None
    return fallback, "Gemini model discovery returned no text models; showing configured fallback models."


__all__ = [
    "GEMINI_MODELS_CACHE_FILENAME",
    "gemini_model_id",
    "is_gemini_text_model",
    "list_gemini_models",
    "read_bundled_gemini_catalog",
    "read_gemini_model_catalog",
    "read_gemini_models_cache",
    "write_gemini_models_cache",
]
