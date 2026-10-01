from __future__ import annotations

from typing import Any

from core.model_client import CompletionResult


def stream_delta_from_chat_completion(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] if isinstance(choices[0], dict) else {}
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
        for key in ("content", "reasoning_content", "reasoning", "thinking"):
            text = str(delta.get(key) or "")
            if text:
                return text
        message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
        for key in ("content", "reasoning_content", "reasoning", "thinking"):
            text = str(message.get(key) or "")
            if text:
                return text
    message = data.get("message") if isinstance(data.get("message"), dict) else {}
    for value in (message.get("content"), message.get("thinking"), data.get("response")):
        text = str(value or "")
        if text:
            return text
    return ""


def chat_completion_usage(data: dict[str, Any], finish_reason: Any = None) -> dict[str, Any]:
    usage_data = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    return {
        "prompt_tokens": usage_data.get("prompt_tokens"),
        "completion_tokens": usage_data.get("completion_tokens"),
        "total_tokens": usage_data.get("total_tokens"),
        "finish_reason": finish_reason,
    }


def first_chat_completion_choice(data: dict[str, Any]) -> dict[str, Any]:
    choices = data.get("choices") if isinstance(data.get("choices"), list) else []
    return choices[0] if choices and isinstance(choices[0], dict) else {}


def completion_result_from_chat_completion(data: dict[str, Any], *, model: str) -> CompletionResult:
    first_choice = first_chat_completion_choice(data)
    message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
    text = str(message.get("content") or "").strip()
    usage = chat_completion_usage(data, first_choice.get("finish_reason"))
    return CompletionResult(text=text, model=model, usage=usage, raw_response=data)


def completion_result_from_stream(
    *,
    chunks: list[str],
    final_data: dict[str, Any],
    model: str,
) -> CompletionResult:
    text = "".join(chunks).strip()
    finish_reason = first_chat_completion_choice(final_data).get("finish_reason")
    usage = chat_completion_usage(final_data, finish_reason)
    return CompletionResult(text=text, model=model, usage=usage, raw_response=final_data)


__all__ = [
    "chat_completion_usage",
    "completion_result_from_chat_completion",
    "completion_result_from_stream",
    "first_chat_completion_choice",
    "stream_delta_from_chat_completion",
]
