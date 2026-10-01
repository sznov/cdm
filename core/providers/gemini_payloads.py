from __future__ import annotations

from typing import Any

from core.model_client import ChatMessage


GEMINI_OUTPUT_TOKEN_LIMITS = {
    "gemma-4-31b-it": 32768,
    "gemini-3.5-flash": 65536,
    "gemini-3.1-flash-lite-preview": 32768,
}


def gemini_effective_num_predict(model: str, num_predict: int | None) -> int | None:
    if num_predict is None:
        return None
    output_limit = GEMINI_OUTPUT_TOKEN_LIMITS.get(model)
    if output_limit is None:
        return num_predict
    return min(num_predict, output_limit)


def gemini_uses_gemini_3_defaults(model: str) -> bool:
    return model.strip().lower().startswith("gemini-3")


def gemini_chat_messages(
    *,
    system_prompt: str,
    user_content: str,
    messages: list[ChatMessage] | None = None,
) -> list[dict[str, str]]:
    chat_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if messages is None:
        chat_messages.append({"role": "user", "content": user_content})
    else:
        chat_messages.extend({"role": item["role"], "content": item["content"]} for item in messages)
    return chat_messages


def gemini_request_payload(
    *,
    model: str,
    chat_messages: list[dict[str, str]],
    stream: bool,
    num_predict: int | None,
    temperature: float | None,
    top_p: float | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": chat_messages,
        "stream": stream,
    }
    max_tokens = gemini_effective_num_predict(model, num_predict)
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if not gemini_uses_gemini_3_defaults(model):
        if temperature is not None:
            payload["temperature"] = temperature
        if top_p is not None:
            payload["top_p"] = top_p
    return payload


__all__ = [
    "GEMINI_OUTPUT_TOKEN_LIMITS",
    "gemini_chat_messages",
    "gemini_effective_num_predict",
    "gemini_request_payload",
    "gemini_uses_gemini_3_defaults",
]
