from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


NVIDIA_NIM_DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
NVIDIA_NIM_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
NVIDIA_NIM_CATALOG_SCHEMA_VERSION = 1
NVIDIA_NIM_DEFAULT_STALE_AFTER_SECONDS = 7 * 24 * 60 * 60

NVIDIA_NIM_ALLOWED_TEXT_TAGS = {
    "text-to-text",
    "coding",
    "code generation",
    "multimodal",
    "agent",
    "agentic",
    "chat",
    "instruction following",
    "language generation",
    "text-generation",
    "reasoning",
    "advanced reasoning",
}

NVIDIA_NIM_HEURISTIC_TEXT_ID_PATTERNS = (
    "chat",
    "code",
    "coder",
    "codellama",
    "codestral",
    "dbrx",
    "deepseek",
    "dracarys",
    "gemma",
    "glm",
    "gpt-oss",
    "granite",
    "instruct",
    "jamba",
    "kimi",
    "llama",
    "mistral",
    "mixtral",
    "nemotron",
    "palmyra",
    "phi",
    "qwen",
    "recurrentgemma",
    "sarvam",
    "sea-lion",
    "seed-oss",
    "solar",
    "starcoder",
    "yi-large",
    "zamba",
)

NVIDIA_NIM_HEURISTIC_NON_TEXT_ID_PATTERNS = (
    "bge",
    "calibration",
    "clip",
    "content-safety",
    "cosmos",
    "cosmos-predict",
    "detector",
    "embed",
    "embedqa",
    "flux",
    "gliner",
    "grounding",
    "guard",
    "image",
    "nemoguard",
    "neva",
    "ocr",
    "parakeet",
    "parse",
    "pii",
    "radio",
    "rerank",
    "retriever",
    "reward",
    "safety",
    "sam2",
    "stable-diffusion",
    "topic-control",
    "translate",
    "tts",
    "video",
    "vila",
    "vision",
    "vlm",
    "voice",
)

NVIDIA_NIM_RESERVED_MODEL_PARAMETER_KEYS = {
    "authorization",
    "api_key",
    "base_url",
    "headers",
    "messages",
    "model",
    "provider",
    "stream",
    "timeout_seconds",
    "url",
}

COMMON_TEXT_PARAMETER_SCHEMA: dict[str, dict[str, Any]] = {
    "max_tokens": {"type": "integer", "minimum": 1},
    "temperature": {"type": "number", "minimum": 0},
    "top_p": {"type": "number", "minimum": 0, "maximum": 1},
    "stop": {"type": ["string", "array"]},
    "seed": {"type": "integer"},
    "frequency_penalty": {"type": "number"},
    "presence_penalty": {"type": "number"},
}

DEFAULT_MESSAGE_CONSTRAINTS: dict[str, Any] = {
    "supports_system": True,
    "system_must_be_first": True,
    "requires_user_assistant_alternation": False,
    "last_message_role": "user",
    "supports_context_role": False,
    "supports_multimodal_content_parts": False,
}

STRICT_UNKNOWN_MESSAGE_CONSTRAINTS: dict[str, Any] = {
    **DEFAULT_MESSAGE_CONSTRAINTS,
    "requires_user_assistant_alternation": True,
}

PROMPT_ONLY_STRUCTURED_OUTPUT = {
    "supported": False,
    "strategies": ["prompt_only_json"],
    "preferred_strategy": "prompt_only_json",
}

DEFAULT_REASONING = {
    "supported": False,
    "default_enabled": None,
    "include_reasoning_supported_in_streaming": None,
}

DEFAULT_STREAMING_METADATA = {
    "api_supported": True,
    "transport": "sse",
    "granularity": "token",
    "token_incremental": True,
    "caveat": "",
}

NO_STREAMING_METADATA = {
    "api_supported": False,
    "transport": None,
    "granularity": "none",
    "token_incremental": False,
    "caveat": "",
}

DEFAULT_ASYNC_POLLING_METADATA = {
    "supported": False,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def docs_slug_from_model_id(model_id: str) -> str:
    slug = model_id.strip().lower()
    slug = slug.replace("/", "-").replace(".", "-").replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


def build_slug_from_model_id(model_id: str) -> str:
    return model_id.strip().lower()


def canonicalize_build_model_name(name: str) -> str:
    value = str(name or "").strip()
    return re.sub(r"(?<=\d)_(?=\d)", ".", value)


def canonical_build_resource_model_id(raw: dict[str, Any], publisher: str) -> str:
    resource_id = str(raw.get("resourceId") or raw.get("resource_id") or "").strip()
    name = canonicalize_build_model_name(str(raw.get("name") or "").strip() or resource_id.rsplit("/", 1)[-1])
    if publisher and name:
        return f"{publisher}/{name}"
    return canonical_nim_model_id(resource_id)


def provider_owner_from_model_id(model_id: str) -> str:
    return model_id.split("/", 1)[0] if "/" in model_id else ""


def _base_model_metadata(
    model_id: str,
    *,
    label: str | None = None,
    tags: list[str] | None = None,
    description: str = "",
    build_slug: str | None = None,
    docs_slug: str | None = None,
    aliases: list[str] | None = None,
    endpoint_mode: str = "streaming_chat_completions",
    supports_async_polling: bool | None = None,
    streaming: dict[str, Any] | None = None,
    async_polling: dict[str, Any] | None = None,
    input_modalities: list[str] | None = None,
    output_modalities: list[str] | None = None,
    supported_parameters: dict[str, dict[str, Any]] | None = None,
    structured_output: dict[str, Any] | None = None,
    reasoning: dict[str, Any] | None = None,
    message_constraints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    owner = provider_owner_from_model_id(model_id)
    resolved_build_slug = build_slug or build_slug_from_model_id(model_id)
    resolved_docs_slug = docs_slug or docs_slug_from_model_id(model_id)
    tag_values = sorted({tag.strip().lower() for tag in (tags or []) if tag and tag.strip()})
    resolved_supports_streaming = endpoint_mode == "streaming_chat_completions"
    resolved_supports_async_polling = bool(supports_async_polling) if supports_async_polling is not None else endpoint_mode == "async_polling"
    resolved_streaming = deepcopy(
        streaming if streaming is not None else (DEFAULT_STREAMING_METADATA if resolved_supports_streaming else NO_STREAMING_METADATA)
    )
    resolved_async_polling = deepcopy(async_polling or {**DEFAULT_ASYNC_POLLING_METADATA, "supported": resolved_supports_async_polling})
    return {
        "schema_version": NVIDIA_NIM_CATALOG_SCHEMA_VERSION,
        "canonical_model_id": model_id,
        "id": model_id,
        "provider_owner": owner,
        "label": label or model_id,
        "description": description,
        "docs_slug": resolved_docs_slug,
        "build_slug": resolved_build_slug,
        "aliases": sorted({alias for alias in (aliases or []) if alias and alias != model_id}),
        "build_url": f"https://build.nvidia.com/{resolved_build_slug}",
        "model_card_url": f"https://build.nvidia.com/{resolved_build_slug}/modelcard",
        "api_reference_url": f"https://docs.api.nvidia.com/nim/reference/{resolved_docs_slug}",
        "free_endpoint": True,
        "endpoint_available": True,
        "catalog_known": True,
        "stale": False,
        "stale_after_seconds": NVIDIA_NIM_DEFAULT_STALE_AFTER_SECONDS,
        "last_seen_in_v1_models": None,
        "last_seen_in_build": None,
        "removed_from_source_at": None,
        "source_last_success_at": {},
        "source_last_error": {},
        "sources": {
            "model_id": "builtin_seed",
            "free_endpoint": "builtin_seed",
            "tags": "builtin_seed",
            "parameters": "builtin_seed",
            "message_constraints": "builtin_seed",
        },
        "confidence": {
            "model_id": "medium",
            "free_endpoint": "medium",
            "parameters": "low",
            "message_constraints": "low",
        },
        "tags": tag_values,
        "input_modalities": input_modalities or ["text"],
        "output_modalities": output_modalities or ["text"],
        "endpoint_family": "chat_completions",
        "endpoint_mode": endpoint_mode,
        "invoke_url_template": "{base_url}/chat/completions",
        "status_url_template": None,
        "polling_request_id_source": None,
        "supports_streaming": resolved_supports_streaming,
        "supports_non_streaming": endpoint_mode in {"streaming_chat_completions", "sync_chat_completions"},
        "supports_async_polling": resolved_supports_async_polling,
        "streaming": resolved_streaming,
        "async_polling": resolved_async_polling,
        "supported_parameters": deepcopy(supported_parameters or COMMON_TEXT_PARAMETER_SCHEMA),
        "unsupported_parameters": [],
        "unsupported_parameter_combinations": [],
        "known_error_quirks": [
            {"status": 500, "pattern": "model", "normalize_to": "unsupported_model"},
            {"status": 400, "pattern": "unsupported", "normalize_to": "unsupported_parameter"},
        ],
        "structured_output": deepcopy(structured_output or PROMPT_ONLY_STRUCTURED_OUTPUT),
        "reasoning": deepcopy(reasoning or DEFAULT_REASONING),
        "message_constraints": deepcopy(message_constraints or DEFAULT_MESSAGE_CONSTRAINTS),
    }


NVIDIA_NIM_BUILTIN_MODELS: list[dict[str, Any]] = [
    _base_model_metadata(
        "nvidia/nemotron-3-super-120b-a12b",
        label="Nemotron 3 Super 120B A12B",
        tags=["chat", "reasoning", "instruction following", "text-to-text", "language generation"],
        description="NVIDIA Nemotron 3 Super 120B A12B Free Endpoint.",
        docs_slug="nvidia-nemotron-3-super-120b-a12b",
    ),
    _base_model_metadata(
        "google/diffusiongemma-26b-a4b-it",
        label="Diffusion Gemma 26B A4B IT",
        tags=["chat", "reasoning", "instruction following", "text-to-text", "language generation"],
        description="Google Diffusion Gemma 26B A4B IT Free Endpoint.",
        docs_slug="diffusiongemma-26b-a4b-it",
        endpoint_mode="streaming_chat_completions",
        supports_async_polling=True,
        streaming={
            "api_supported": True,
            "transport": "sse",
            "granularity": "block_or_chunk",
            "token_incremental": False,
            "caveat": "Diffusion model denoises/commits blocks; short completions may arrive as one or few chunks.",
        },
        async_polling={"supported": True},
    ),
    _base_model_metadata(
        "minimaxai/minimax-m3",
        label="minimax-m3",
        tags=["coding", "text-to-text", "reasoning", "chat", "multimodal", "agent"],
        description="MiniMax M3 Preview Free Endpoint.",
        supports_async_polling=True,
        async_polling={"supported": True},
        input_modalities=["text", "image"],
        output_modalities=["text"],
        message_constraints={
            **STRICT_UNKNOWN_MESSAGE_CONSTRAINTS,
            "supports_context_role": True,
            "supports_multimodal_content_parts": True,
        },
    ),
    _base_model_metadata(
        "moonshotai/kimi-k2.6",
        label="Kimi-K2.6",
        tags=["coding", "reasoning", "chat", "text-to-text", "agentic"],
        description="MoonshotAI Kimi-K2.6 Free Endpoint.",
        docs_slug="moonshotai-kimi-k2-6",
        aliases=["moonshotai/kimi-k2-6"],
        supports_async_polling=True,
        async_polling={"supported": True},
        input_modalities=["text", "image", "video"],
        output_modalities=["text"],
        message_constraints={
            **DEFAULT_MESSAGE_CONSTRAINTS,
            "supports_multimodal_content_parts": True,
        },
    ),
]


def builtin_nvidia_nim_catalog() -> list[dict[str, Any]]:
    return deepcopy(NVIDIA_NIM_BUILTIN_MODELS)


def alias_map(entries: list[dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for entry in entries:
        canonical = str(entry.get("canonical_model_id") or entry.get("id") or "").strip()
        if not canonical:
            continue
        aliases[canonical.lower()] = canonical
        for key in ("docs_slug", "build_slug"):
            value = str(entry.get(key) or "").strip()
            if value:
                aliases[value.lower()] = canonical
        for value in entry.get("aliases") or []:
            if isinstance(value, str) and value.strip():
                aliases[value.strip().lower()] = canonical
    return aliases


def canonical_nim_model_id(model: str, entries: list[dict[str, Any]] | None = None) -> str:
    value = str(model or "").strip()
    if not value:
        return NVIDIA_NIM_DEFAULT_MODEL
    resolved = alias_map(entries or builtin_nvidia_nim_catalog()).get(value.lower())
    return resolved or value


def nvidia_nim_model_by_id(model: str, entries: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    canonical = canonical_nim_model_id(model, entries)
    for entry in entries or builtin_nvidia_nim_catalog():
        if str(entry.get("canonical_model_id") or entry.get("id")) == canonical:
            return deepcopy(entry)
    return None


def unknown_nvidia_nim_model_metadata(model: str) -> dict[str, Any]:
    metadata = _base_model_metadata(
        canonical_nim_model_id(model),
        label=canonical_nim_model_id(model),
        tags=[],
        description="Custom NVIDIA NIM model with conservative OpenAI-compatible assumptions.",
        endpoint_mode="sync_chat_completions",
        message_constraints=STRICT_UNKNOWN_MESSAGE_CONSTRAINTS,
    )
    metadata["free_endpoint"] = None
    metadata["endpoint_available"] = None
    metadata["catalog_known"] = False
    metadata["stale"] = True
    metadata["sources"] = {"model_id": "custom_user_input"}
    metadata["confidence"] = {"model_id": "low", "parameters": "low", "message_constraints": "low"}
    return metadata


def nvidia_nim_model_id_looks_text_generating(model_id: str) -> bool:
    value = str(model_id or "").strip().lower()
    if not value:
        return False
    if any(pattern in value for pattern in NVIDIA_NIM_HEURISTIC_NON_TEXT_ID_PATTERNS):
        return False
    return any(pattern in value for pattern in NVIDIA_NIM_HEURISTIC_TEXT_ID_PATTERNS)


def heuristic_nvidia_nim_text_model_metadata(model_id: str) -> dict[str, Any]:
    canonical = canonical_nim_model_id(model_id)
    tags = ["chat", "language generation", "text-generation", "text-to-text"]
    lowered = canonical.lower()
    if any(pattern in lowered for pattern in ("code", "coder", "codellama", "codestral", "starcoder")):
        tags.append("coding")
    if any(pattern in lowered for pattern in ("reason", "deepseek", "gpt-oss", "nemotron", "qwen")):
        tags.append("reasoning")
    metadata = _base_model_metadata(
        canonical,
        label=canonical,
        tags=tags,
        description="Endpoint-discovered NVIDIA NIM text model with heuristic chat-completions metadata.",
        endpoint_mode="streaming_chat_completions",
        message_constraints=DEFAULT_MESSAGE_CONSTRAINTS,
    )
    metadata["free_endpoint"] = None
    metadata["catalog_known"] = True
    metadata["sources"] = {
        **metadata.get("sources", {}),
        "free_endpoint": "unknown",
        "tags": "hosted_v1_models_heuristic",
        "parameters": "common_chat_completion_defaults",
        "message_constraints": "conservative_default",
    }
    metadata["confidence"] = {
        **metadata.get("confidence", {}),
        "free_endpoint": "low",
        "tags": "low",
        "parameters": "low",
        "message_constraints": "low",
    }
    return metadata


def nvidia_nim_metadata_is_v1_heuristic(metadata: dict[str, Any]) -> bool:
    sources = metadata.get("sources")
    return isinstance(sources, dict) and sources.get("tags") == "hosted_v1_models_heuristic"


def metadata_for_nvidia_nim_model(model: str, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return nvidia_nim_model_by_id(model, entries) or unknown_nvidia_nim_model_metadata(model)


def _source_timestamp_map(value: Any) -> dict[str, str]:
    return value if isinstance(value, dict) else {}


def merge_v1_model_ids(
    entries: list[dict[str, Any]],
    model_ids: list[str],
    *,
    observed_at: str | None = None,
) -> list[dict[str, Any]]:
    now = observed_at or utc_now_iso()
    by_id = {canonical_nim_model_id(str(entry.get("canonical_model_id") or entry.get("id")), entries): deepcopy(entry) for entry in entries}
    seen = {model_id.strip() for model_id in model_ids if model_id and model_id.strip()}
    for model_id in sorted(seen):
        canonical = canonical_nim_model_id(model_id, entries)
        entry = by_id.get(canonical)
        looks_text_generating = nvidia_nim_model_id_looks_text_generating(canonical)
        if entry is not None and nvidia_nim_metadata_is_v1_heuristic(entry) and not looks_text_generating:
            entry = unknown_nvidia_nim_model_metadata(canonical)
        elif entry is None:
            entry = (
                heuristic_nvidia_nim_text_model_metadata(canonical)
                if looks_text_generating
                else unknown_nvidia_nim_model_metadata(canonical)
            )
        entry["canonical_model_id"] = canonical
        entry["id"] = canonical
        entry["endpoint_available"] = True
        entry["stale"] = False
        entry["last_seen_in_v1_models"] = now
        entry["removed_from_source_at"] = None
        entry["source_last_success_at"] = {**_source_timestamp_map(entry.get("source_last_success_at")), "hosted_v1_models": now}
        entry.setdefault("sources", {})["model_id"] = "hosted_v1_models"
        entry.setdefault("confidence", {})["model_id"] = "high"
        by_id[canonical] = entry
    for canonical, entry in by_id.items():
        if canonical not in seen and entry.get("last_seen_in_v1_models"):
            entry["endpoint_available"] = False
            entry["removed_from_source_at"] = entry.get("removed_from_source_at") or now
            entry["stale"] = True
    return sorted(by_id.values(), key=lambda item: str(item.get("canonical_model_id") or item.get("id")).lower())


def normalize_build_resource(raw: dict[str, Any], *, observed_at: str | None = None) -> dict[str, Any] | None:
    labels = raw.get("labels") if isinstance(raw.get("labels"), list) else []
    tags: set[str] = set()
    free_endpoint = False
    publisher = ""
    for label in labels:
        if not isinstance(label, dict):
            continue
        key = str(label.get("key") or "").strip().lower()
        values = [str(value).strip() for value in label.get("values") or [] if str(value).strip()]
        lowered = {value.lower() for value in values}
        if key == "general":
            tags.update(lowered)
        if key == "nimtype" and "free endpoint" in lowered:
            free_endpoint = True
        if key == "publisher" and values:
            publisher = values[0]
    if not free_endpoint or not tags.intersection(NVIDIA_NIM_ALLOWED_TEXT_TAGS):
        return None
    resource_id = canonical_build_resource_model_id(raw, publisher)
    if "/" not in resource_id:
        return None
    entry = _base_model_metadata(
        resource_id,
        label=str(raw.get("displayName") or raw.get("display_name") or resource_id),
        tags=sorted(tags),
        description=str(raw.get("description") or ""),
        build_slug=resource_id,
    )
    if publisher:
        entry["provider_owner"] = publisher
    now = observed_at or utc_now_iso()
    entry["last_seen_in_build"] = now
    entry["source_last_success_at"] = {"build_models_page": now}
    entry["sources"]["free_endpoint"] = "build_models_page"
    entry["sources"]["tags"] = "build_models_page"
    entry["confidence"]["free_endpoint"] = "medium"
    return entry


def _build_catalog_json_text(html: str) -> str:
    return html.replace("\\\\", "\\").replace('\\"', '"')


def _extract_balanced_json_object(text: str, start: int) -> dict[str, Any] | None:
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    level = 0
    in_string = False
    escaped = False
    for index, character in enumerate(text[start:], start):
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            level += 1
        elif character == "}":
            level -= 1
            if level == 0:
                try:
                    decoded = json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    return None
                return decoded if isinstance(decoded, dict) else None
    return None


def _iter_build_search_results(html: str) -> list[dict[str, Any]]:
    text = _build_catalog_json_text(html)
    results: list[dict[str, Any]] = []
    key = '"searchResult":'
    offset = 0
    while True:
        key_index = text.find(key, offset)
        if key_index < 0:
            break
        start = text.find("{", key_index + len(key))
        decoded = _extract_balanced_json_object(text, start)
        if decoded and isinstance(decoded.get("results"), list):
            results.append(decoded)
        offset = key_index + len(key)
    return results


def parse_build_catalog_resources(html: str) -> list[dict[str, Any]]:
    resources_by_id: dict[str, dict[str, Any]] = {}
    # The Build page embeds JSON inside Next.js flight chunks. This parser is intentionally
    # tolerant and best-effort for the manual refresh command, not a runtime dependency.
    for search_result in _iter_build_search_results(html):
        for result_group in search_result.get("results") or []:
            if not isinstance(result_group, dict):
                continue
            for resource in result_group.get("resources") or []:
                if not isinstance(resource, dict):
                    continue
                normalized = normalize_build_resource(resource)
                if normalized:
                    resources_by_id[str(normalized.get("canonical_model_id") or normalized.get("id"))] = normalized
    return sorted(resources_by_id.values(), key=lambda item: str(item.get("canonical_model_id") or item.get("id")).lower())


def model_has_text_output(metadata: dict[str, Any]) -> bool:
    outputs = {str(value).lower() for value in metadata.get("output_modalities") or []}
    endpoint_family = str(metadata.get("endpoint_family") or "")
    return "text" in outputs and endpoint_family in {"chat_completions", "text_completions"}


def nim_model_matches_requested_tags(metadata: dict[str, Any]) -> bool:
    tags = {str(value).strip().lower() for value in metadata.get("tags") or []}
    return bool(tags.intersection(NVIDIA_NIM_ALLOWED_TEXT_TAGS))


def nim_model_is_eligible_for_text_harness(metadata: dict[str, Any]) -> bool:
    model_id = str(metadata.get("canonical_model_id") or metadata.get("id") or "").lower()
    if any(pattern in model_id for pattern in NVIDIA_NIM_HEURISTIC_NON_TEXT_ID_PATTERNS):
        return False
    return model_has_text_output(metadata) and nim_model_matches_requested_tags(metadata)


def nim_model_is_confirmed_free_endpoint(metadata: dict[str, Any]) -> bool:
    return metadata.get("free_endpoint") is True


def nvidia_nim_model_options(
    entries: list[dict[str, Any]] | None = None,
    *,
    include_unconfirmed_free_endpoint: bool = False,
    endpoint_available_only: bool = False,
) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for metadata in entries or builtin_nvidia_nim_catalog():
        if not nim_model_is_eligible_for_text_harness(metadata):
            continue
        if not include_unconfirmed_free_endpoint and not nim_model_is_confirmed_free_endpoint(metadata):
            continue
        if endpoint_available_only and metadata.get("endpoint_available") is False:
            continue
        canonical = str(metadata.get("canonical_model_id") or metadata.get("id") or "")
        options.append(
            {
                "id": canonical,
                "model": canonical,
                "value": canonical,
                "name": metadata.get("label") or canonical,
                "label": metadata.get("label") or canonical,
                "catalog_known": metadata.get("catalog_known", True),
                "endpoint_available": metadata.get("endpoint_available"),
                "free_endpoint": metadata.get("free_endpoint"),
                "stale": bool(metadata.get("stale")),
                "tags": metadata.get("tags") or [],
                "input_modalities": metadata.get("input_modalities") or ["text"],
                "output_modalities": metadata.get("output_modalities") or ["text"],
                "endpoint_family": metadata.get("endpoint_family") or "unknown",
                "endpoint_mode": metadata.get("endpoint_mode") or "unknown",
                "supports_streaming": bool(metadata.get("supports_streaming")),
                "supports_non_streaming": bool(metadata.get("supports_non_streaming")),
                "supports_async_polling": bool(metadata.get("supports_async_polling")),
                "streaming": metadata.get("streaming") or NO_STREAMING_METADATA,
                "async_polling": metadata.get("async_polling") or DEFAULT_ASYNC_POLLING_METADATA,
                "aliases": metadata.get("aliases") or [],
                "docs_slug": metadata.get("docs_slug"),
                "build_slug": metadata.get("build_slug"),
                "api_reference_url": metadata.get("api_reference_url"),
                "build_url": metadata.get("build_url"),
                "message_constraints": metadata.get("message_constraints") or DEFAULT_MESSAGE_CONSTRAINTS,
                "supported_parameters": metadata.get("supported_parameters") or {},
                "unsupported_parameters": metadata.get("unsupported_parameters") or [],
                "unsupported_parameter_combinations": metadata.get("unsupported_parameter_combinations") or [],
                "structured_output": metadata.get("structured_output") or PROMPT_ONLY_STRUCTURED_OUTPUT,
            }
        )
    return sorted(options, key=lambda option: str(option.get("label") or option.get("id")).lower())


def _condition_matches(parameters: dict[str, Any], condition: dict[str, Any]) -> bool:
    for key, expected in condition.items():
        if parameters.get(key) != expected:
            return False
    return True


def validate_nvidia_nim_model_parameters(
    metadata: dict[str, Any],
    parameters: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized = deepcopy(parameters or {})
    for key in normalized:
        if key.lower() in NVIDIA_NIM_RESERVED_MODEL_PARAMETER_KEYS:
            raise ValueError(f"NVIDIA NIM model parameter '{key}' is reserved and cannot be set here.")
    supported = metadata.get("supported_parameters") if isinstance(metadata.get("supported_parameters"), dict) else {}
    unsupported = {str(key) for key in metadata.get("unsupported_parameters") or []}
    allowed = set(supported)
    for key in normalized:
        if key in unsupported:
            raise ValueError(f"NVIDIA NIM model parameter '{key}' is not supported by {metadata.get('canonical_model_id')}.")
        if allowed and key not in allowed:
            raise ValueError(
                f"NVIDIA NIM model parameter '{key}' is not declared for {metadata.get('canonical_model_id')}. "
                f"Allowed parameters: {', '.join(sorted(allowed))}."
            )
    for rule in metadata.get("unsupported_parameter_combinations") or []:
        if not isinstance(rule, dict):
            continue
        condition = rule.get("when") if isinstance(rule.get("when"), dict) else {}
        reject_keys = [str(key) for key in rule.get("reject_keys") or []]
        if condition and _condition_matches(normalized, condition) and any(key in normalized for key in reject_keys):
            message = str(rule.get("message") or "Unsupported NVIDIA NIM parameter combination.")
            raise ValueError(message)
    return normalized


def nvidia_nim_parameters_from_binding(
    metadata: dict[str, Any],
    *,
    model_parameters: dict[str, Any] | None = None,
    max_completion_tokens: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
) -> dict[str, Any]:
    raw = deepcopy(model_parameters or {})
    supported = metadata.get("supported_parameters") if isinstance(metadata.get("supported_parameters"), dict) else {}
    mapped: dict[str, Any] = {}
    if max_completion_tokens is not None:
        if "max_tokens" in raw:
            raise ValueError("Set either max_completion_tokens or model_parameters.max_tokens, not both.")
        mapped["max_tokens"] = max_completion_tokens
    if temperature is not None:
        if "temperature" in raw:
            raise ValueError("Set either temperature or model_parameters.temperature, not both.")
        mapped["temperature"] = temperature
    if top_p is not None:
        if "top_p" in raw:
            raise ValueError("Set either top_p or model_parameters.top_p, not both.")
        mapped["top_p"] = top_p
    filtered = {key: value for key, value in {**mapped, **raw}.items() if value is not None}
    if supported:
        filtered = {key: value for key, value in filtered.items() if key in supported or key in raw}
    return validate_nvidia_nim_model_parameters(metadata, filtered)


__all__ = [
    "COMMON_TEXT_PARAMETER_SCHEMA",
    "DEFAULT_MESSAGE_CONSTRAINTS",
    "NVIDIA_NIM_ALLOWED_TEXT_TAGS",
    "NVIDIA_NIM_CATALOG_SCHEMA_VERSION",
    "NVIDIA_NIM_DEFAULT_BASE_URL",
    "NVIDIA_NIM_DEFAULT_MODEL",
    "NVIDIA_NIM_RESERVED_MODEL_PARAMETER_KEYS",
    "PROMPT_ONLY_STRUCTURED_OUTPUT",
    "STRICT_UNKNOWN_MESSAGE_CONSTRAINTS",
    "builtin_nvidia_nim_catalog",
    "canonical_nim_model_id",
    "heuristic_nvidia_nim_text_model_metadata",
    "merge_v1_model_ids",
    "metadata_for_nvidia_nim_model",
    "model_has_text_output",
    "nim_model_is_confirmed_free_endpoint",
    "nim_model_is_eligible_for_text_harness",
    "nvidia_nim_model_id_looks_text_generating",
    "nvidia_nim_model_by_id",
    "nvidia_nim_model_options",
    "nvidia_nim_parameters_from_binding",
    "normalize_build_resource",
    "parse_build_catalog_resources",
    "unknown_nvidia_nim_model_metadata",
    "validate_nvidia_nim_model_parameters",
]
