from __future__ import annotations

import json
from typing import Any

import httpx

from core.config_safety import redact_sensitive_text, safe_exception_detail
from core.model_client import TextModelClient
from core.providers.factory import build_text_model_client, provider_descriptor
from harnesses.contracts import EffectiveHarnessRunSpec
from harnesses.provenance import RunProvenance, canonical_sha256

def optional_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def optional_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def correction_client_from_run_record(record: dict[str, Any]) -> tuple[str, str, str, TextModelClient]:
    spec = EffectiveHarnessRunSpec.model_validate(record.get("effective_harness_run_spec"))
    provenance = RunProvenance.model_validate(record.get("provenance"))
    binding = spec.model_bindings["default"]
    provider_identity = provenance.provider
    if (
        binding.provider != provider_identity.provider_id
        or binding.model != provider_identity.model_id
        or canonical_sha256(binding) != provider_identity.binding_sha256
    ):
        raise ValueError("Recorded correction binding does not match sealed run provenance.")
    default_binding = binding.model_dump(mode="json")
    provider_id = binding.provider
    model_name = binding.model
    base_url = str(binding.base_url or "")
    if not base_url:
        raise ValueError("Recorded correction binding has no frozen endpoint.")
    provider_options = dict(binding.provider_options)
    catalog_entries = provider_identity.execution_catalog_entries()
    if catalog_entries is not None:
        provider_options["catalog_entries"] = catalog_entries
    client = build_text_model_client(
        provider=provider_id,
        model=model_name,
        base_url=default_binding.get("base_url"),
        max_completion_tokens=optional_int(default_binding.get("max_completion_tokens"), 32768),
        temperature=optional_float(default_binding.get("temperature")),
        top_p=optional_float(default_binding.get("top_p")),
        timeout_seconds=optional_float(default_binding.get("timeout_seconds"), 600.0) or 600.0,
        reasoning_effort=default_binding.get("reasoning_effort"),
        provider_options=provider_options,
        model_parameters=default_binding.get("model_parameters") if isinstance(default_binding.get("model_parameters"), dict) else None,
    )
    return provider_id, model_name, base_url, client

def model_call_error_detail(provider: str, exc: BaseException) -> str:
    try:
        label = provider_descriptor(provider).label
    except ValueError:
        label = str(provider or "Provider")
    if isinstance(exc, httpx.HTTPStatusError):
        detail = f"{label} returned {exc.response.status_code}."
        try:
            payload = exc.response.json()
            error_detail = payload.get("error") or payload.get("message") or payload.get("detail")
            if isinstance(error_detail, dict):
                error_detail = error_detail.get("message") or json.dumps(error_detail, ensure_ascii=False)
            if error_detail:
                detail = f"{detail} {error_detail}"
        except (ValueError, httpx.ResponseNotRead, httpx.StreamClosed, httpx.StreamConsumed):
            pass
        return redact_sensitive_text(detail)
    if isinstance(exc, httpx.RequestError):
        return redact_sensitive_text(f"{label} request failed: {safe_exception_detail(exc)}")
    return redact_sensitive_text(f"{label} model call failed: {safe_exception_detail(exc)}")


__all__ = [
    "correction_client_from_run_record",
    "model_call_error_detail",
    "optional_float",
    "optional_int",
]
