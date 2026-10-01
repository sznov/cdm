from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.config_safety import (
    validate_endpoint_url,
    validate_secret_free_mapping,
)
from core.providers.factory import provider_descriptor
from core.providers.nvidia_nim_catalog import (
    canonical_nim_model_id,
    metadata_for_nvidia_nim_model,
    model_has_text_output,
    nvidia_nim_parameters_from_binding,
    validate_nvidia_nim_model_parameters,
)


def validate_model_binding_security(
    binding: dict[str, Any] | None,
    *,
    path: str = "model_bindings.default",
) -> None:
    """Validate the credential-free durable model-binding boundary."""

    if not isinstance(binding, dict):
        return
    for url_field in ("base_url", "gemini_base_url"):
        if url_field in binding:
            validate_endpoint_url(binding.get(url_field), field_name=f"{path}.{url_field}")
    for container_name in ("provider_options", "model_parameters"):
        container = binding.get(container_name)
        if container is not None:
            validate_secret_free_mapping(container, path=f"{path}.{container_name}")


def validate_model_bindings_security(bindings: dict[str, Any] | None) -> None:
    """Validate raw or fully resolved bindings without normalizing or mutating them."""

    if not isinstance(bindings, dict):
        return
    direct_binding_fields = {
        "provider",
        "model",
        "base_url",
        "gemini_base_url",
        "provider_options",
        "model_parameters",
    }
    if direct_binding_fields.intersection(bindings):
        validate_model_binding_security(bindings)
        return
    for slot, binding in bindings.items():
        if isinstance(binding, dict):
            validate_model_binding_security(binding, path=f"model_bindings.{slot}")


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def default_model_binding(provider: str | None = "gemini") -> dict[str, Any]:
    descriptor = provider_descriptor(provider)
    return {
        "provider": descriptor.id,
        "model": descriptor.default_model,
        "base_url": descriptor.default_base_url,
        "max_completion_tokens": 32768,
        "temperature": None,
        "top_p": None,
        "timeout_seconds": 600.0,
        "reasoning_effort": "xhigh" if descriptor.supports_reasoning_effort else None,
        "provider_options": {},
        "model_parameters": {},
    }


def normalize_model_binding(binding: dict[str, Any] | None, *, fallback_provider: str | None = "gemini") -> dict[str, Any]:
    raw = dict(binding or {})
    validate_model_binding_security(raw)
    for field in ("provider", "model"):
        if field in raw and not str(raw.get(field) or "").strip():
            raise ValueError(f"Model binding {field} must be nonempty.")
    provider = str(raw.get("provider") or fallback_provider or "gemini").strip().lower()
    normalized = default_model_binding(provider)
    if raw.get("model") not in (None, ""):
        normalized["model"] = str(raw["model"]).strip()
    if provider == "nvidia_nim":
        normalized["model"] = canonical_nim_model_id(str(normalized["model"]))
    if "base_url" in raw:
        normalized["base_url"] = str(raw["base_url"]).strip().rstrip("/") if raw.get("base_url") else None
    elif raw.get("gemini_base_url"):
        normalized["base_url"] = str(raw["gemini_base_url"]).strip().rstrip("/")
    if "max_completion_tokens" in raw:
        normalized["max_completion_tokens"] = _optional_int(raw.get("max_completion_tokens"))
    elif "num_predict" in raw:
        normalized["max_completion_tokens"] = _optional_int(raw.get("num_predict"))
    if "temperature" in raw:
        normalized["temperature"] = _optional_float(raw.get("temperature"))
    if "top_p" in raw:
        normalized["top_p"] = _optional_float(raw.get("top_p"))
    if "timeout_seconds" in raw:
        normalized["timeout_seconds"] = _optional_float(raw.get("timeout_seconds")) or 600.0
    if raw.get("reasoning_effort") not in (None, ""):
        normalized["reasoning_effort"] = str(raw["reasoning_effort"]).strip()
    if isinstance(raw.get("provider_options"), dict):
        normalized["provider_options"] = deepcopy(raw["provider_options"])
    if isinstance(raw.get("model_parameters"), dict):
        normalized["model_parameters"] = deepcopy(raw["model_parameters"])
    return normalized


def normalize_model_bindings(bindings: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    raw = bindings if isinstance(bindings, dict) else {}
    default_binding = raw.get("default") if isinstance(raw.get("default"), dict) else raw if raw else None
    return {"default": normalize_model_binding(default_binding)}


def validate_model_binding_capabilities(
    binding: dict[str, Any],
    *,
    supported_providers: list[str] | tuple[str, ...] | None = None,
    required_capabilities: dict[str, Any] | None = None,
    nvidia_nim_catalog_entries: list[dict[str, Any]] | None = None,
    catalog_metadata_is_advisory: bool = False,
) -> None:
    normalized = normalize_model_binding(binding)
    provider = str(normalized["provider"])
    if supported_providers and provider not in set(supported_providers):
        allowed = ", ".join(supported_providers)
        raise ValueError(f"Provider '{provider}' is not supported by this harness. Choose one of: {allowed}.")
    descriptor = provider_descriptor(provider)
    metadata: dict[str, Any] | None = None
    if provider == "nvidia_nim":
        model = str(normalized.get("model") or "")
        metadata = (
            {"canonical_model_id": model, "supported_parameters": {}}
            if catalog_metadata_is_advisory
            else metadata_for_nvidia_nim_model(model, nvidia_nim_catalog_entries)
        )
        if not catalog_metadata_is_advisory:
            if metadata.get("endpoint_available") is False:
                raise ValueError(f"NVIDIA NIM model '{model}' is not available on the configured endpoint.")
            if not model_has_text_output(metadata):
                raise ValueError(f"NVIDIA NIM model '{model}' is not a supported text-output model.")
        validate_nvidia_nim_model_parameters(metadata, normalized.get("model_parameters") or {})
        nvidia_nim_parameters_from_binding(
            metadata,
            model_parameters=normalized.get("model_parameters") if isinstance(normalized.get("model_parameters"), dict) else None,
            max_completion_tokens=normalized.get("max_completion_tokens"),
            temperature=normalized.get("temperature"),
            top_p=normalized.get("top_p"),
        )
    requirements = required_capabilities or {}
    checks = {
        "streaming": descriptor.supports_streaming,
        "token_incremental_streaming": descriptor.supports_streaming,
        "json_response": descriptor.supports_json_response,
        "reasoning_effort": descriptor.supports_reasoning_effort,
    }
    if provider == "nvidia_nim" and not catalog_metadata_is_advisory:
        assert metadata is not None
        streaming = metadata.get("streaming") if isinstance(metadata.get("streaming"), dict) else {}
        checks["streaming"] = bool(metadata.get("supports_streaming"))
        checks["token_incremental_streaming"] = bool(streaming.get("token_incremental"))
        checks["json_response"] = bool(descriptor.supports_json_response)
    for name, required in requirements.items():
        if bool(required) and not checks.get(name, False):
            if provider == "nvidia_nim":
                model = str(normalized.get("model") or "selected model")
                raise ValueError(f"NVIDIA NIM model '{model}' does not support required capability '{name}'.")
            raise ValueError(f"Provider '{provider}' does not support required capability '{name}'.")


__all__ = [
    "default_model_binding",
    "normalize_model_binding",
    "normalize_model_bindings",
    "validate_model_binding_security",
    "validate_model_bindings_security",
    "validate_model_binding_capabilities",
]
