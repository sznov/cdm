from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from core.config_safety import redact_persisted_value, safe_exception_detail


T = TypeVar("T")


@dataclass(slots=True)
class RefillAttempt(Generic[T]):
    attempt_index: int
    valid_index: int | None
    status: str
    value: T | None = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RefillResult(Generic[T]):
    target_valid: int
    values: list[T]
    attempts: list[RefillAttempt[T]]

    @property
    def exhausted(self) -> bool:
        return len(self.values) < self.target_valid


AttemptCallable = Callable[[int], Awaitable[T]]


async def collect_valid_attempts(
    *,
    target_valid: int,
    max_attempts: int,
    run_attempt: AttemptCallable[T],
    metadata_for_attempt: Callable[[int], dict[str, Any]] | None = None,
) -> RefillResult[T]:
    """Run attempts until enough valid values are collected or attempts are exhausted."""
    if target_valid < 0:
        raise ValueError("target_valid must be non-negative")
    if max_attempts < 0:
        raise ValueError("max_attempts must be non-negative")
    values: list[T] = []
    attempts: list[RefillAttempt[T]] = []
    attempt_index = 0
    while len(values) < target_valid and attempt_index < max_attempts:
        attempt_index += 1
        metadata = metadata_for_attempt(attempt_index) if metadata_for_attempt is not None else {}
        safe_metadata = redact_persisted_value(metadata)
        try:
            value = await run_attempt(attempt_index)
        except Exception as exc:
            attempts.append(
                RefillAttempt(
                    attempt_index=attempt_index,
                    valid_index=None,
                    status="failed",
                    error=safe_exception_detail(exc),
                    metadata=safe_metadata,
                )
            )
            continue
        values.append(value)
        attempts.append(
            RefillAttempt(
                attempt_index=attempt_index,
                valid_index=len(values),
                status="valid",
                value=value,
                metadata=safe_metadata,
            )
        )
    return RefillResult(target_valid=target_valid, values=values, attempts=attempts)


__all__ = ["RefillAttempt", "RefillResult", "collect_valid_attempts"]
