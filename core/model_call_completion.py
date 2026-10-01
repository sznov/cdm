from __future__ import annotations

import asyncio
from collections import deque
from functools import partial
from typing import Any

from core.model_call_logger import ModelCallLogger
from core.model_call_retry import (
    DEFAULT_TRANSPORT_RETRIES,
    DEFAULT_TRANSPORT_RETRY_BACKOFF_BASE_SECONDS,
    DEFAULT_TRANSPORT_RETRY_BACKOFF_MAX_SECONDS,
    model_call_transport_error_is_retryable,
    model_call_transport_retry_delay_seconds,
)
from core.model_client import ChatMessage, CompletionResult, TextModelClient
from core.providers.factory import provider_descriptor


MAX_MODEL_CALL_DIAGNOSTIC_BYTES = 1024 * 1024
_DIAGNOSTIC_CHUNK_COALESCE_BYTES = 16 * 1024


class _DiagnosticUtf8Tail:
    """Incremental byte-bounded output tail with valid UTF-8 boundaries."""

    def __init__(self, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("Diagnostic output byte limit must be positive.")
        self._max_bytes = max_bytes
        self._chunks: deque[bytes] = deque()
        self._retained_bytes = 0
        self._streamed_bytes = 0
        self._prefix_truncated = False

    @property
    def streamed_bytes(self) -> int:
        return self._streamed_bytes

    @property
    def retained_bytes(self) -> int:
        return self._retained_bytes

    @property
    def prefix_truncated(self) -> bool:
        return self._prefix_truncated

    def append(self, value: str) -> None:
        encoded = value.encode("utf-8")
        if not encoded:
            return
        self._streamed_bytes += len(encoded)
        if (
            self._chunks
            and len(self._chunks[-1]) + len(encoded)
            <= _DIAGNOSTIC_CHUNK_COALESCE_BYTES
        ):
            self._chunks[-1] += encoded
        else:
            self._chunks.append(encoded)
        self._retained_bytes += len(encoded)
        self._trim_prefix()

    def text(self) -> str:
        return b"".join(self._chunks).decode("utf-8")

    def release(self) -> None:
        self._chunks.clear()
        self._retained_bytes = 0
        self._prefix_truncated = False

    def _trim_prefix(self) -> None:
        excess = self._retained_bytes - self._max_bytes
        while excess > 0 and self._chunks:
            first = self._chunks[0]
            if len(first) <= excess:
                self._chunks.popleft()
                self._retained_bytes -= len(first)
                excess -= len(first)
                self._prefix_truncated = True
                continue
            cut = excess
            while cut < len(first) and first[cut] & 0xC0 == 0x80:
                cut += 1
            self._chunks[0] = first[cut:]
            self._retained_bytes -= cut
            self._prefix_truncated = True
            excess = 0


def _diagnostic_metadata(
    capture: _DiagnosticUtf8Tail,
) -> dict[str, int | bool]:
    return {
        "streamed_bytes_observed": capture.streamed_bytes,
        "diagnostic_bytes_retained": capture.retained_bytes,
        "diagnostic_prefix_truncated": capture.prefix_truncated,
    }


async def _run_atomic_log_write(function: Any, /, *args: Any, **kwargs: Any) -> Any:
    """Finish an already-started transcript publication before cancellation."""

    task = asyncio.create_task(asyncio.to_thread(partial(function, *args, **kwargs)))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        try:
            task.result()
        except BaseException:
            pass
        raise cancellation


async def complete_with_logging(
    *,
    client: TextModelClient,
    logger: ModelCallLogger,
    kind: str,
    system_prompt: str,
    user_content: str,
    messages: list[ChatMessage] | None = None,
    on_token: Any | None = None,
    metadata: dict[str, Any] | None = None,
    transport_retries: int | None = None,
    transport_retry_backoff_base_seconds: float = DEFAULT_TRANSPORT_RETRY_BACKOFF_BASE_SECONDS,
    transport_retry_backoff_max_seconds: float = DEFAULT_TRANSPORT_RETRY_BACKOFF_MAX_SECONDS,
    transport_retry_sleep: Any | None = None,
    diagnostic_capture_max_bytes: int = MAX_MODEL_CALL_DIAGNOSTIC_BYTES,
) -> tuple[CompletionResult, dict[str, Any] | None]:
    if diagnostic_capture_max_bytes < 1:
        raise ValueError("Diagnostic output byte limit must be positive.")
    if transport_retries is None:
        provider_id = getattr(client, "provider_id", None) or getattr(client, "provider", None)
        try:
            transport_retries = provider_descriptor(str(provider_id)).default_transport_retries if provider_id else DEFAULT_TRANSPORT_RETRIES
        except ValueError:
            transport_retries = DEFAULT_TRANSPORT_RETRIES
    max_transport_attempts = max(1, int(transport_retries or 0) + 1)
    base_metadata = dict(metadata or {})
    sleep = transport_retry_sleep or asyncio.sleep
    for transport_attempt in range(1, max_transport_attempts + 1):
        reservation = await asyncio.to_thread(logger.reserve, kind)
        diagnostic_tail = _DiagnosticUtf8Tail(
            diagnostic_capture_max_bytes
        )

        async def logged_on_token(delta: str) -> None:
            if delta:
                diagnostic_tail.append(delta)
            if on_token is None:
                return
            maybe_awaitable = on_token(delta)
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable

        attempt_metadata = {
            **base_metadata,
            "transport_attempt": transport_attempt,
            "transport_max_attempts": max_transport_attempts,
        }
        try:
            completion = await client.complete(
                system_prompt=system_prompt,
                user_content=user_content,
                messages=messages,
                on_token=logged_on_token if on_token is not None else None,
            )
        except asyncio.CancelledError as exc:
            diagnostic_metadata = _diagnostic_metadata(diagnostic_tail)
            partial_text = diagnostic_tail.text().strip()
            diagnostic_tail.release()
            partial_completion = (
                CompletionResult(
                    text=partial_text,
                    model=str(getattr(client, "model", "unknown-model")),
                    usage=None,
                    raw_response={"partial_output": True, "cancelled": True},
                )
                if partial_text
                else None
            )
            await _run_atomic_log_write(
                logger.write,
                kind=kind,
                system_prompt=system_prompt,
                user_content=user_content,
                messages=messages,
                completion=partial_completion,
                error=exc,
                metadata={
                    **attempt_metadata,
                    "partial_output_captured": bool(partial_text),
                    "cancelled": True,
                    **diagnostic_metadata,
                },
                reservation=reservation,
            )
            raise
        except Exception as exc:
            diagnostic_metadata = _diagnostic_metadata(diagnostic_tail)
            partial_text = diagnostic_tail.text().strip()
            diagnostic_tail.release()
            partial_completion = (
                CompletionResult(
                    text=partial_text,
                    model=str(getattr(client, "model", "unknown-model")),
                    usage=None,
                    raw_response={"partial_output": True, "error": repr(exc)},
                )
                if partial_text
                else None
            )
            retryable = model_call_transport_error_is_retryable(exc)
            will_retry = retryable and transport_attempt < max_transport_attempts
            retry_delay_seconds = (
                model_call_transport_retry_delay_seconds(
                    transport_attempt=transport_attempt,
                    base_delay_seconds=transport_retry_backoff_base_seconds,
                    max_delay_seconds=transport_retry_backoff_max_seconds,
                )
                if will_retry
                else 0.0
            )
            await _run_atomic_log_write(
                logger.write,
                kind=kind,
                system_prompt=system_prompt,
                user_content=user_content,
                messages=messages,
                completion=partial_completion,
                error=exc,
                metadata={
                    **attempt_metadata,
                    "partial_output_captured": bool(partial_text),
                    "will_retry": will_retry,
                    "transport_retry_delay_seconds": retry_delay_seconds,
                    **diagnostic_metadata,
                },
                reservation=reservation,
            )
            if not will_retry:
                raise
            maybe_awaitable = sleep(retry_delay_seconds)
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable
            continue

        provider_diagnostics = None
        if isinstance(completion.raw_response, dict):
            provider_diagnostics = completion.raw_response.get("provider_diagnostics")
        successful_streamed_bytes = diagnostic_tail.streamed_bytes
        diagnostic_tail.release()
        successful_diagnostic_metadata = {
            "streamed_bytes_observed": successful_streamed_bytes,
            "diagnostic_bytes_retained": 0,
            "diagnostic_prefix_truncated": False,
        }
        log_metadata = (
            {
                **attempt_metadata,
                **successful_diagnostic_metadata,
                "provider_diagnostics": provider_diagnostics,
            }
            if isinstance(provider_diagnostics, dict)
            else {
                **attempt_metadata,
                **successful_diagnostic_metadata,
            }
        )
        log_record = await _run_atomic_log_write(
            logger.write,
            kind=kind,
            system_prompt=system_prompt,
            user_content=user_content,
            messages=messages,
            completion=completion,
            metadata=log_metadata,
            reservation=reservation,
        )
        return completion, log_record

    raise RuntimeError("Model completion retry loop exited without a completion.")


__all__ = [
    "MAX_MODEL_CALL_DIAGNOSTIC_BYTES",
    "complete_with_logging",
]
