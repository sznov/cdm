from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx

from core.model_client import ChatMessage, CompletionResult
from core.providers.gemini_payloads import (
    GEMINI_OUTPUT_TOKEN_LIMITS,
    gemini_chat_messages,
    gemini_effective_num_predict,
    gemini_request_payload,
    gemini_uses_gemini_3_defaults,
)
from core.providers.gemini_responses import (
    completion_result_from_chat_completion,
    completion_result_from_stream,
    stream_delta_from_chat_completion,
)


@dataclass
class GeminiOpenAICompatibleClient:
    provider_id: ClassVar[str] = "gemini"

    model: str
    base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    api_key: str | None = None
    num_predict: int | None = 32768
    temperature: float | None = None
    top_p: float | None = None
    timeout_seconds: float = 600.0

    def effective_num_predict(self) -> int | None:
        return gemini_effective_num_predict(self.model, self.num_predict)

    def uses_gemini_3_defaults(self) -> bool:
        return gemini_uses_gemini_3_defaults(self.model)

    def request_payload(self, chat_messages: list[dict[str, str]], *, stream: bool) -> dict[str, Any]:
        return gemini_request_payload(
            model=self.model,
            chat_messages=chat_messages,
            stream=stream,
            num_predict=self.num_predict,
            temperature=self.temperature,
            top_p=self.top_p,
        )

    def resolved_api_key(self) -> str:
        key = (self.api_key or os.getenv("GEMINI_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it in API key settings, .env, or the process environment.")
        return key

    def chat_completions_url(self) -> str:
        base = self.base_url.strip().rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    async def complete(
        self,
        *,
        system_prompt: str,
        user_content: str,
        messages: list[ChatMessage] | None = None,
        on_token: Any | None = None,
    ) -> CompletionResult:
        chat_messages = gemini_chat_messages(
            system_prompt=system_prompt,
            user_content=user_content,
            messages=messages,
        )
        payload = self.request_payload(chat_messages, stream=bool(on_token))

        headers = {
            "Authorization": f"Bearer {self.resolved_api_key()}",
            "Content-Type": "application/json",
        }
        url = self.chat_completions_url()

        async def emit_token(delta: str) -> None:
            if not delta or on_token is None:
                return
            maybe_awaitable = on_token(delta)
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable

        if on_token is not None:
            chunks: list[str] = []
            final_data: dict[str, Any] = {}
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip() or line.startswith(":"):
                            continue
                        raw_data = line.removeprefix("data:").strip()
                        if raw_data == "[DONE]":
                            break
                        data = json.loads(raw_data)
                        final_data = data
                        delta = stream_delta_from_chat_completion(data)
                        if delta:
                            chunks.append(delta)
                            await emit_token(delta)
            return completion_result_from_stream(chunks=chunks, final_data=final_data, model=self.model)

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
        return completion_result_from_chat_completion(response.json(), model=self.model)
