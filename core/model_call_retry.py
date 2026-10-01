from __future__ import annotations

import json

import httpx


DEFAULT_TRANSPORT_RETRIES = 3
DEFAULT_GEMINI_TRANSPORT_RETRIES = 10
DEFAULT_TRANSPORT_RETRY_BACKOFF_BASE_SECONDS = 0.5
DEFAULT_TRANSPORT_RETRY_BACKOFF_MAX_SECONDS = 8.0


def model_call_transport_retry_delay_seconds(
    *,
    transport_attempt: int,
    base_delay_seconds: float = DEFAULT_TRANSPORT_RETRY_BACKOFF_BASE_SECONDS,
    max_delay_seconds: float = DEFAULT_TRANSPORT_RETRY_BACKOFF_MAX_SECONDS,
) -> float:
    retry_index = max(0, transport_attempt - 1)
    base_delay = max(0.0, float(base_delay_seconds))
    max_delay = max(0.0, float(max_delay_seconds))
    if base_delay <= 0.0 or max_delay <= 0.0:
        return 0.0
    return min(max_delay, base_delay * (2**retry_index))


def model_call_transport_error_is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code in {408, 409, 425, 429} or 500 <= status_code <= 599
    return isinstance(exc, (httpx.RequestError, json.JSONDecodeError))


__all__ = [
    "DEFAULT_GEMINI_TRANSPORT_RETRIES",
    "DEFAULT_TRANSPORT_RETRIES",
    "DEFAULT_TRANSPORT_RETRY_BACKOFF_BASE_SECONDS",
    "DEFAULT_TRANSPORT_RETRY_BACKOFF_MAX_SECONDS",
    "model_call_transport_error_is_retryable",
    "model_call_transport_retry_delay_seconds",
]
