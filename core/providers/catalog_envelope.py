from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from core.atomic_io import atomic_write_text


PROVIDER_CATALOG_SCHEMA_VERSION = 1
ProviderCatalogId = Literal["gemini", "nvidia_nim"]
ProviderCatalogSource = Literal["live", "persisted", "bundled"]
ProviderCatalogOrigin = Literal["live", "bundled"]

_STALE_AFTER = {
    "gemini": timedelta(hours=24),
    "nvidia_nim": timedelta(days=7),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProviderCatalogEnvelope(BaseModel):
    """Versioned model-catalog boundary shared by persistence and the API."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = PROVIDER_CATALOG_SCHEMA_VERSION
    provider_id: ProviderCatalogId
    source: ProviderCatalogSource
    origin: ProviderCatalogOrigin
    retrieved_at_utc: datetime
    stale: bool
    unverified: bool
    warning: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    models: list[dict[str, Any]] = Field(min_length=1)

    @field_validator("retrieved_at_utc")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at_utc must include a UTC offset")
        return value.astimezone(timezone.utc)

    @field_validator("models")
    @classmethod
    def require_model_ids(cls, models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen_ids: set[str] = set()
        for model in models:
            raw_model_id = model.get("id") or model.get("canonical_model_id")
            if not isinstance(raw_model_id, str) or not raw_model_id.strip():
                raise ValueError("every provider catalog model must have an id")
            model_id = raw_model_id.strip()
            if model_id in seen_ids:
                raise ValueError(f"duplicate provider catalog model id: {model_id}")
            seen_ids.add(model_id)
        return models

    @model_validator(mode="after")
    def enforce_delivery_invariants(self) -> ProviderCatalogEnvelope:
        if self.source == "bundled" and self.origin != "bundled":
            raise ValueError("bundled delivery must have bundled origin")
        if self.source in {"live", "persisted"} and self.origin != "live":
            raise ValueError("live and persisted deliveries must have live origin")
        if self.source == "bundled" and (not self.stale or not self.unverified):
            raise ValueError("bundled catalogs must be stale and unverified")
        if self.source == "bundled" and (not self.warning or not self.provenance):
            raise ValueError("bundled catalogs must include warning and provenance labels")
        if self.source == "live" and (self.stale or self.unverified):
            raise ValueError("live catalogs cannot be stale or unverified")
        if self.source == "persisted" and self.unverified:
            raise ValueError("persisted live-discovery catalogs cannot be unverified")
        return self

    @field_serializer("retrieved_at_utc")
    def serialize_retrieved_at(self, value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    def detached_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def with_models(self, models: list[dict[str, Any]]) -> ProviderCatalogEnvelope:
        """Return a revalidated detached envelope with a projected model list."""

        payload = self.detached_dict()
        payload["models"] = models
        return ProviderCatalogEnvelope.model_validate(payload)


def catalog_is_stale(
    provider_id: ProviderCatalogId,
    retrieved_at_utc: datetime,
    *,
    now: datetime | None = None,
) -> bool:
    checked_at = (now or utc_now()).astimezone(timezone.utc)
    return checked_at - retrieved_at_utc.astimezone(timezone.utc) >= _STALE_AFTER[provider_id]


def persisted_catalog(
    envelope: ProviderCatalogEnvelope,
    *,
    now: datetime | None = None,
) -> ProviderCatalogEnvelope:
    stale = catalog_is_stale(envelope.provider_id, envelope.retrieved_at_utc, now=now)
    warning = envelope.warning
    if stale:
        warning = warning or "The last successfully discovered model catalog is stale."
    return envelope.model_copy(
        update={
            "source": "persisted",
            "origin": "live",
            "stale": stale,
            "unverified": False,
            "warning": warning,
        },
        deep=True,
    )


def catalog_with_warning(
    envelope: ProviderCatalogEnvelope,
    warning: str | None,
) -> ProviderCatalogEnvelope:
    message = (warning or "").strip()
    if not message:
        return envelope
    existing = (envelope.warning or "").strip()
    combined = message if not existing else f"{message} {existing}"
    return envelope.model_copy(update={"warning": combined}, deep=True)


def live_catalog(
    provider_id: ProviderCatalogId,
    models: list[dict[str, Any]],
    *,
    retrieved_at_utc: datetime | None = None,
    provenance: dict[str, Any] | None = None,
) -> ProviderCatalogEnvelope:
    return ProviderCatalogEnvelope(
        provider_id=provider_id,
        source="live",
        origin="live",
        retrieved_at_utc=retrieved_at_utc or utc_now(),
        stale=False,
        unverified=False,
        warning=None,
        provenance=provenance or {},
        models=models,
    )


def read_persisted_catalog(
    path: Path,
    *,
    provider_id: ProviderCatalogId,
    now: datetime | None = None,
) -> ProviderCatalogEnvelope | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        envelope = ProviderCatalogEnvelope.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if envelope.provider_id != provider_id or envelope.origin != "live":
        return None
    return persisted_catalog(envelope, now=now)


def write_catalog(path: Path, envelope: ProviderCatalogEnvelope) -> None:
    atomic_write_text(
        path,
        json.dumps(envelope.detached_dict(), ensure_ascii=False, indent=2) + "\n",
    )


__all__ = [
    "PROVIDER_CATALOG_SCHEMA_VERSION",
    "ProviderCatalogEnvelope",
    "ProviderCatalogId",
    "ProviderCatalogOrigin",
    "ProviderCatalogSource",
    "catalog_with_warning",
    "catalog_is_stale",
    "live_catalog",
    "persisted_catalog",
    "read_persisted_catalog",
    "utc_now",
    "write_catalog",
]
