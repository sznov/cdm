from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.services.runtime_gemini_models import (
    read_gemini_model_catalog,
)
from backend.services.runtime_nvidia_nim_models import (
    read_nvidia_nim_model_catalog,
)
from core.providers.catalog_envelope import ProviderCatalogEnvelope
from core.config_safety import (
    provider_environment_endpoint_url,
    validate_endpoint_url,
)
from core.providers.factory import provider_descriptor
from core.providers.nvidia_nim_catalog import (
    canonical_nim_model_id,
    metadata_for_nvidia_nim_model,
)
from harnesses.contracts import EffectiveHarnessRunSpec
from harnesses.provenance import (
    ProviderExecutionIdentity,
    canonical_sha256,
    endpoint_class_for_provider,
    with_frozen_default_binding,
)


@dataclass(frozen=True, slots=True)
class RuntimeExecutionSnapshot:
    spec: EffectiveHarnessRunSpec
    provider: ProviderExecutionIdentity

    def __post_init__(self) -> None:
        object.__setattr__(self, "spec", self.spec.detached_copy())
        object.__setattr__(self, "provider", self.provider.model_copy(deep=True))


def _resolved_endpoint(provider_id: str, configured: str | None) -> str:
    descriptor = provider_descriptor(provider_id)
    environment_value = provider_environment_endpoint_url(provider_id)
    configured_value = str(configured or "").strip().rstrip("/")
    default_value = str(descriptor.default_base_url or "").strip().rstrip("/")
    resolved = (
        environment_value
        if environment_value and configured_value in {"", default_value}
        else configured_value or environment_value or default_value
    )
    if not resolved:
        raise ValueError(f"Provider {provider_id!r} has no effective endpoint.")
    return resolved.rstrip("/")


def _catalog_fields(catalog: ProviderCatalogEnvelope) -> dict[str, Any]:
    payload = catalog.detached_dict()
    return {
        "catalog_source": catalog.source,
        "catalog_origin": catalog.origin,
        "catalog_retrieved_at_utc": payload["retrieved_at_utc"],
        "catalog_stale": catalog.stale,
        "catalog_unverified": catalog.unverified,
    }


def _gemini_selected_metadata(catalog: ProviderCatalogEnvelope, model_id: str) -> dict[str, Any] | None:
    normalized = model_id.removeprefix("models/")
    for entry in catalog.models:
        candidate = str(entry.get("id") or entry.get("name") or "")
        if candidate == model_id or candidate.removeprefix("models/") == normalized:
            return dict(entry)
    return None


def materialize_runtime_execution_snapshot(
    spec: EffectiveHarnessRunSpec,
    *,
    gemini_catalog_path: Path,
    nvidia_catalog_path: Path,
) -> RuntimeExecutionSnapshot:
    """Freeze endpoint and catalog-derived execution metadata before queueing."""

    binding = spec.model_bindings["default"]
    provider_id = binding.provider
    endpoint = _resolved_endpoint(provider_id, binding.base_url)
    validate_endpoint_url(endpoint, field_name=f"{provider_id} effective endpoint")
    model_id = binding.model
    selected_metadata: dict[str, Any] | None = None
    catalog_fields: dict[str, Any] = {
        "catalog_source": "not_applicable",
        "catalog_origin": "not_applicable",
    }
    if provider_id == "gemini":
        catalog = read_gemini_model_catalog(gemini_catalog_path)
        catalog_fields = _catalog_fields(catalog)
        selected_metadata = _gemini_selected_metadata(catalog, model_id)
    elif provider_id == "nvidia_nim":
        catalog = read_nvidia_nim_model_catalog(nvidia_catalog_path)
        catalog_fields = _catalog_fields(catalog)
        model_id = canonical_nim_model_id(model_id, catalog.models)
        selected_metadata = metadata_for_nvidia_nim_model(model_id, catalog.models)

    frozen_spec = with_frozen_default_binding(spec, model_id=model_id, endpoint=endpoint)
    provider = ProviderExecutionIdentity(
        provider_id=provider_id,
        model_id=model_id,
        binding_sha256=canonical_sha256(frozen_spec.model_bindings["default"]),
        endpoint_class=endpoint_class_for_provider(provider_id, endpoint),
        selected_model_metadata=selected_metadata,
        selected_model_metadata_sha256=(
            canonical_sha256(selected_metadata) if selected_metadata is not None else None
        ),
        **catalog_fields,
    )
    return RuntimeExecutionSnapshot(spec=frozen_spec, provider=provider)


__all__ = [
    "RuntimeExecutionSnapshot",
    "materialize_runtime_execution_snapshot",
]
