from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, ClassVar

import httpx

from core.model_client import ChatMessage, CompletionResult
from core.providers.gemini_responses import (
    completion_result_from_chat_completion,
    completion_result_from_stream,
    stream_delta_from_chat_completion,
)
from core.providers.nvidia_nim_catalog import (
    DEFAULT_MESSAGE_CONSTRAINTS,
    NVIDIA_NIM_DEFAULT_BASE_URL,
    NVIDIA_NIM_DEFAULT_MODEL,
    canonical_nim_model_id,
    metadata_for_nvidia_nim_model,
    nvidia_nim_parameters_from_binding,
)


class NvidiaNimProviderError(RuntimeError):
    def __init__(self, message: str, *, category: str = "provider_error") -> None:
        super().__init__(message)
        self.category = category


def _string_content(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    raise NvidiaNimProviderError("NVIDIA NIM provider currently supports text-only message content.")


def _replace_content(message: dict[str, Any], content: str) -> dict[str, str]:
    return {"role": str(message.get("role") or "user"), "content": content}


def _non_system_roles(messages: list[dict[str, str]]) -> list[str]:
    return [message["role"] for message in messages if message.get("role") != "system"]


def _validate_alternating_roles(messages: list[dict[str, str]]) -> None:
    roles = _non_system_roles(messages)
    previous: str | None = None
    for role in roles:
        if role not in {"user", "assistant"}:
            raise NvidiaNimProviderError(f"NVIDIA NIM message role '{role}' is not supported by this model.")
        if previous == role:
            raise NvidiaNimProviderError(
                "NVIDIA NIM model requires alternating user/assistant messages; "
                f"found consecutive '{role}' messages."
            )
        previous = role


def apply_nvidia_nim_message_constraints(
    *,
    system_prompt: str,
    user_content: str,
    messages: list[ChatMessage] | None,
    constraints: dict[str, Any] | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    resolved_constraints = {**DEFAULT_MESSAGE_CONSTRAINTS, **dict(constraints or {})}
    transformations: list[str] = []
    raw_messages: list[dict[str, Any]]
    if messages is None:
        raw_messages = [{"role": "user", "content": user_content}]
    else:
        raw_messages = [dict(message) for message in messages]

    if not resolved_constraints.get("supports_multimodal_content_parts", False):
        for raw in raw_messages:
            _string_content(raw)

    if resolved_constraints.get("supports_system", True):
        prepared: list[dict[str, str]] = []
        raw_has_system = any(str(raw.get("role") or "") == "system" for raw in raw_messages)
        if system_prompt and not raw_has_system:
            prepared.append({"role": "system", "content": system_prompt})
        prepared.extend(_replace_content(raw, _string_content(raw)) for raw in raw_messages)
    else:
        system_parts = [system_prompt] if system_prompt else []
        system_parts.extend(_string_content(raw) for raw in raw_messages if raw.get("role") == "system")
        first_user_index = next((index for index, raw in enumerate(raw_messages) if raw.get("role") == "user"), None)
        if system_parts and first_user_index is None:
            raise NvidiaNimProviderError("NVIDIA NIM model does not support system messages and no user message exists.")
        prepared = []
        for index, raw in enumerate(raw_messages):
            if raw.get("role") == "system":
                continue
            content = _string_content(raw)
            if system_parts and index == first_user_index:
                combined_system = "\n\n".join(system_parts)
                content = f"SYSTEM:\n{combined_system}\n\nUSER:\n{content}"
                transformations.append("folded_system_prompt_into_first_user_message")
            prepared.append(_replace_content(raw, content))

    if resolved_constraints.get("system_must_be_first", True):
        for index, message in enumerate(prepared):
            if message["role"] == "system" and index != 0:
                raise NvidiaNimProviderError("NVIDIA NIM model requires system messages to appear first.")

    if resolved_constraints.get("requires_user_assistant_alternation", False):
        _validate_alternating_roles(prepared)

    last_role = resolved_constraints.get("last_message_role")
    if last_role == "user":
        roles = _non_system_roles(prepared)
        if roles and roles[-1] != "user":
            raise NvidiaNimProviderError("NVIDIA NIM model requires the final message role to be 'user'.")

    return prepared, transformations


def _request_id_from_response(response: httpx.Response, data: dict[str, Any]) -> str | None:
    for header in ("NVCF-REQID", "nvcf-reqid", "x-request-id", "location"):
        value = response.headers.get(header)
        if value:
            return value.rsplit("/", 1)[-1]
    for key in ("request_id", "requestId", "id"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _polling_result_payload(data: dict[str, Any]) -> dict[str, Any]:
    response = data.get("response") if isinstance(data.get("response"), dict) else None
    result = data.get("result") if isinstance(data.get("result"), dict) else None
    return response or result or data


async def _response_error_text(response: httpx.Response) -> str:
    try:
        return response.text
    except httpx.ResponseNotRead:
        body = await response.aread()
        return body.decode("utf-8", errors="replace")


@dataclass
class NvidiaNimClient:
    provider_id: ClassVar[str] = "nvidia_nim"

    model: str = NVIDIA_NIM_DEFAULT_MODEL
    base_url: str = NVIDIA_NIM_DEFAULT_BASE_URL
    api_key: str | None = None
    max_completion_tokens: int | None = 32768
    temperature: float | None = None
    top_p: float | None = None
    timeout_seconds: float = 600.0
    model_parameters: dict[str, Any] | None = None
    catalog_entries: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None
    poll_interval_seconds: float = 1.0
    transformations: list[str] = field(default_factory=list)

    def resolved_api_key(self) -> str:
        key = (self.api_key or os.getenv("NVIDIA_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("NVIDIA_API_KEY is not set. Add it in API key settings, .env, or the process environment.")
        return key

    def resolved_base_url(self) -> str:
        return (self.base_url or os.getenv("NVIDIA_NIM_BASE_URL") or NVIDIA_NIM_DEFAULT_BASE_URL).rstrip("/")

    def model_metadata(self) -> dict[str, Any]:
        return self.metadata or metadata_for_nvidia_nim_model(self.model, self.catalog_entries)

    def canonical_model(self) -> str:
        return canonical_nim_model_id(self.model, self.catalog_entries)

    def chat_completions_url(self) -> str:
        base = self.resolved_base_url()
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def status_url(self, request_id: str) -> str | None:
        metadata = self.model_metadata()
        template = metadata.get("status_url_template")
        if isinstance(template, str) and template:
            return template.format(base_url=self.resolved_base_url(), request_id=request_id)
        return f"{self.resolved_base_url()}/status/{request_id}"

    def request_payload(self, chat_messages: list[dict[str, str]], *, stream: bool) -> dict[str, Any]:
        metadata = self.model_metadata()
        parameters = nvidia_nim_parameters_from_binding(
            metadata,
            model_parameters=self.model_parameters,
            max_completion_tokens=self.max_completion_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
        )
        payload: dict[str, Any] = {
            "model": canonical_nim_model_id(self.model, self.catalog_entries),
            "messages": chat_messages,
            "stream": stream,
            **parameters,
        }
        return payload

    def _provider_diagnostics(
        self,
        *,
        endpoint_mode: str,
        stream_requested: bool,
        async_polling: bool = False,
        async_request_id: str | None = None,
        sse_event_count: int = 0,
        content_delta_count: int = 0,
        first_delta_after_seconds: float | None = None,
    ) -> dict[str, Any]:
        return {
            "provider": "nvidia_nim",
            "endpoint_mode": endpoint_mode,
            "stream_requested": stream_requested,
            "async_polling": async_polling,
            "async_request_id": async_request_id,
            "sse_event_count": sse_event_count,
            "content_delta_count": content_delta_count,
            "first_delta_after_seconds": first_delta_after_seconds,
        }

    async def raise_for_provider_error(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        text = await _response_error_text(response)
        lowered = text.lower()
        for quirk in self.model_metadata().get("known_error_quirks") or []:
            if not isinstance(quirk, dict):
                continue
            status = quirk.get("status")
            if status is not None and int(status) != response.status_code:
                continue
            pattern = str(quirk.get("pattern") or "").strip().lower()
            if pattern and pattern not in lowered:
                continue
            category = str(quirk.get("normalize_to") or "provider_error")
            raise NvidiaNimProviderError(
                f"NVIDIA NIM {category}: HTTP {response.status_code}: {text[:800]}",
                category=category,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise NvidiaNimProviderError(
                f"NVIDIA NIM provider returned HTTP {response.status_code}: {text[:800]}",
                category="provider_error",
            ) from exc

    async def _poll_result(
        self,
        client: httpx.AsyncClient,
        *,
        headers: dict[str, str],
        request_id: str,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + self.timeout_seconds
        url = self.status_url(request_id)
        if not url:
            raise NvidiaNimProviderError("NVIDIA NIM async response did not provide a status URL.")
        while True:
            response = await client.get(url, headers=headers)
            if response.status_code == 202:
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError(f"NVIDIA NIM async request {request_id} timed out.")
                await asyncio.sleep(self.poll_interval_seconds)
                continue
            await self.raise_for_provider_error(response)
            data = response.json()
            return _polling_result_payload(data if isinstance(data, dict) else {})

    async def _post_non_streaming(
        self,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> CompletionResult:
        endpoint_mode = str(self.model_metadata().get("endpoint_mode") or "sync_chat_completions")
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.chat_completions_url(), json=payload, headers=headers)
            if response.status_code == 202:
                data = response.json() if response.content else {}
                request_id = _request_id_from_response(response, data if isinstance(data, dict) else {})
                if not request_id:
                    await self.raise_for_provider_error(response)
                final_data = await self._poll_result(client, headers=headers, request_id=request_id)
                completion = completion_result_from_chat_completion(final_data, model=self.canonical_model())
                completion.raw_response = {
                    **(completion.raw_response or {}),
                    "nvidia_nim_async_request_id": request_id,
                    "provider_diagnostics": self._provider_diagnostics(
                        endpoint_mode=endpoint_mode,
                        stream_requested=False,
                        async_polling=True,
                        async_request_id=request_id,
                    ),
                    "message_transformations": list(self.transformations),
                }
                return completion
            await self.raise_for_provider_error(response)
            data = response.json()
        completion = completion_result_from_chat_completion(data, model=self.canonical_model())
        completion.raw_response = {
            **(completion.raw_response or {}),
            "provider_diagnostics": self._provider_diagnostics(
                endpoint_mode=endpoint_mode,
                stream_requested=False,
            ),
            "message_transformations": list(self.transformations),
        }
        return completion

    async def complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        messages: list[ChatMessage] | None = None,
        on_token: Any | None = None,
    ) -> CompletionResult:
        metadata = self.model_metadata()
        chat_messages, transformations = apply_nvidia_nim_message_constraints(
            system_prompt=system_prompt,
            user_content=user_content,
            messages=messages,
            constraints=metadata.get("message_constraints") if isinstance(metadata.get("message_constraints"), dict) else None,
        )
        self.transformations = transformations
        endpoint_mode = str(metadata.get("endpoint_mode") or "sync_chat_completions")
        stream = bool(on_token) and endpoint_mode == "streaming_chat_completions"
        payload = self.request_payload(chat_messages, stream=stream)
        headers = {
            "Authorization": f"Bearer {self.resolved_api_key()}",
            "Content-Type": "application/json",
        }

        if not stream:
            completion = await self._post_non_streaming(payload=payload, headers=headers)
            if on_token is not None and completion.text:
                maybe_awaitable = on_token(completion.text)
                if hasattr(maybe_awaitable, "__await__"):
                    await maybe_awaitable
            return completion

        async def emit_token(delta: str) -> None:
            if not delta or on_token is None:
                return
            maybe_awaitable = on_token(delta)
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable

        chunks: list[str] = []
        final_data: dict[str, Any] = {}
        async_polling = False
        async_request_id: str | None = None
        sse_event_count = 0
        content_delta_count = 0
        first_delta_after_seconds: float | None = None
        request_started = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async with client.stream("POST", self.chat_completions_url(), json=payload, headers=headers) as response:
                if response.status_code == 202:
                    async_polling = True
                    body = await response.aread()
                    data = json.loads(body.decode("utf-8")) if body else {}
                    request_id = _request_id_from_response(response, data if isinstance(data, dict) else {})
                    if not request_id:
                        await self.raise_for_provider_error(response)
                    async_request_id = request_id
                    final_data = await self._poll_result(client, headers=headers, request_id=request_id)
                    delta = stream_delta_from_chat_completion(final_data)
                    if delta:
                        chunks.append(delta)
                        content_delta_count += 1
                        first_delta_after_seconds = round(time.monotonic() - request_started, 3)
                        await emit_token(delta)
                else:
                    await self.raise_for_provider_error(response)
                    async for line in response.aiter_lines():
                        if not line.strip() or line.startswith(":"):
                            continue
                        raw_data = re.sub(r"^data:\s*", "", line).strip()
                        if raw_data == "[DONE]":
                            break
                        data = json.loads(raw_data)
                        if isinstance(data, dict):
                            sse_event_count += 1
                            final_data = data
                            delta = stream_delta_from_chat_completion(data)
                            if delta:
                                chunks.append(delta)
                                content_delta_count += 1
                                if first_delta_after_seconds is None:
                                    first_delta_after_seconds = round(time.monotonic() - request_started, 3)
                                await emit_token(delta)
        completion = completion_result_from_stream(chunks=chunks, final_data=final_data, model=self.canonical_model())
        completion.raw_response = {
            **(completion.raw_response or {}),
            "provider_diagnostics": self._provider_diagnostics(
                endpoint_mode=endpoint_mode,
                stream_requested=True,
                async_polling=async_polling,
                async_request_id=async_request_id,
                sse_event_count=sse_event_count,
                content_delta_count=content_delta_count,
                first_delta_after_seconds=first_delta_after_seconds,
            ),
            "message_transformations": list(self.transformations),
        }
        return completion


__all__ = [
    "NVIDIA_NIM_DEFAULT_BASE_URL",
    "NVIDIA_NIM_DEFAULT_MODEL",
    "NvidiaNimClient",
    "NvidiaNimProviderError",
    "apply_nvidia_nim_message_constraints",
]
