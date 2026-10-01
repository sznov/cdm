from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from core.config_safety import selected_provider_endpoint_url, validate_secret_free_mapping
from core.model_call_retry import DEFAULT_GEMINI_TRANSPORT_RETRIES, DEFAULT_TRANSPORT_RETRIES
from core.model_client import TextModelClient
from core.providers.codex import DEFAULT_CODEX_MODEL, CodexResponsesClient
from core.providers.gemini import GeminiOpenAICompatibleClient
from core.providers.nvidia_nim import NVIDIA_NIM_DEFAULT_BASE_URL, NVIDIA_NIM_DEFAULT_MODEL, NvidiaNimClient


DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
DEFAULT_GEMINI_MODEL = "gemma-4-31b-it"


ProviderName = Literal["gemini", "codex", "nvidia_nim"]


@dataclass(frozen=True)
class ProviderDescriptor:
    id: str
    label: str
    default_model: str
    default_base_url: str | None
    supports_streaming: bool
    supports_json_response: bool
    supports_reasoning_effort: bool
    default_transport_retries: int

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


PROVIDER_DESCRIPTORS: dict[str, ProviderDescriptor] = {
    "gemini": ProviderDescriptor(
        id="gemini",
        label="Gemini API",
        default_model=DEFAULT_GEMINI_MODEL,
        default_base_url=DEFAULT_GEMINI_BASE_URL,
        supports_streaming=True,
        supports_json_response=True,
        supports_reasoning_effort=False,
        default_transport_retries=DEFAULT_GEMINI_TRANSPORT_RETRIES,
    ),
    "codex": ProviderDescriptor(
        id="codex",
        label="Codex",
        default_model=DEFAULT_CODEX_MODEL,
        default_base_url="https://chatgpt.com/backend-api/codex",
        supports_streaming=False,
        supports_json_response=True,
        supports_reasoning_effort=True,
        default_transport_retries=DEFAULT_TRANSPORT_RETRIES,
    ),
    "nvidia_nim": ProviderDescriptor(
        id="nvidia_nim",
        label="NVIDIA NIM",
        default_model=NVIDIA_NIM_DEFAULT_MODEL,
        default_base_url=NVIDIA_NIM_DEFAULT_BASE_URL,
        supports_streaming=True,
        supports_json_response=True,
        supports_reasoning_effort=True,
        default_transport_retries=DEFAULT_TRANSPORT_RETRIES,
    ),
}


def normalize_provider_id(provider: str | None) -> str:
    normalized = (provider or "gemini").strip().lower()
    if normalized not in PROVIDER_DESCRIPTORS:
        raise ValueError(f"Unsupported provider: {provider!r}")
    return normalized


def provider_descriptor(provider: str | None) -> ProviderDescriptor:
    return PROVIDER_DESCRIPTORS[normalize_provider_id(provider)]


def provider_descriptors_payload() -> dict[str, dict[str, object]]:
    return {provider_id: descriptor.model_dump() for provider_id, descriptor in PROVIDER_DESCRIPTORS.items()}


def default_model_for_provider(provider: str) -> str:
    return str(provider_descriptor(provider).default_model)


def build_text_model_client(
    *,
    provider: str,
    model: str,
    base_url: str | None = None,
    timeout_seconds: float = 900.0,
    max_completion_tokens: int | None = 32768,
    reasoning_effort: str | None = None,
    response_format_json_object: bool = True,
    temperature: float | None = None,
    top_p: float | None = None,
    provider_options: dict[str, object] | None = None,
    model_parameters: dict[str, object] | None = None,
) -> TextModelClient:
    normalized = normalize_provider_id(provider)
    options = dict(provider_options or {})
    parameters = dict(model_parameters or {})
    validate_secret_free_mapping(options, path="provider_options")
    validate_secret_free_mapping(parameters, path="model_parameters")
    if normalized == "gemini":
        resolved_base_url = (
            selected_provider_endpoint_url(normalized, base_url)
            or DEFAULT_GEMINI_BASE_URL
        )
        return GeminiOpenAICompatibleClient(
            model=model,
            base_url=resolved_base_url.rstrip("/"),
            timeout_seconds=timeout_seconds,
            num_predict=max_completion_tokens,
            temperature=temperature,
            top_p=top_p,
        )
    if normalized == "codex":
        resolved_base_url = (
            selected_provider_endpoint_url(normalized, base_url)
            or "https://chatgpt.com/backend-api/codex"
        )
        return CodexResponsesClient(
            model=model,
            base_url=resolved_base_url,
            timeout_seconds=timeout_seconds,
            max_completion_tokens=max_completion_tokens,
            reasoning_effort=reasoning_effort or "xhigh",
            response_format_json_object=response_format_json_object,
        )
    if normalized == "nvidia_nim":
        catalog_entries = options.get("catalog_entries")
        resolved_base_url = (
            selected_provider_endpoint_url(normalized, base_url)
            or NVIDIA_NIM_DEFAULT_BASE_URL
        )
        return NvidiaNimClient(
            model=model,
            base_url=resolved_base_url.rstrip("/"),
            timeout_seconds=timeout_seconds,
            max_completion_tokens=max_completion_tokens,
            temperature=temperature,
            top_p=top_p,
            model_parameters=parameters,
            catalog_entries=catalog_entries if isinstance(catalog_entries, list) else None,
        )
    raise ValueError(f"Unsupported provider: {provider!r}")


__all__ = [
    "DEFAULT_CODEX_MODEL",
    "DEFAULT_GEMINI_BASE_URL",
    "DEFAULT_GEMINI_MODEL",
    "NVIDIA_NIM_DEFAULT_BASE_URL",
    "NVIDIA_NIM_DEFAULT_MODEL",
    "ProviderName",
    "PROVIDER_DESCRIPTORS",
    "ProviderDescriptor",
    "build_text_model_client",
    "default_model_for_provider",
    "normalize_provider_id",
    "provider_descriptor",
    "provider_descriptors_payload",
]
