from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TypeVar


_T = TypeVar("_T")


def consume_task_result(task: asyncio.Task[object]) -> None:
    """Observe a detached task result without extending a shutdown deadline."""

    if task.cancelled():
        return
    try:
        task.exception()
    except asyncio.CancelledError:
        return


@dataclass(frozen=True, slots=True)
class ShutdownDeadline:
    """One monotonic application-shutdown budget shared by every owner.

    The deadline bounds how long shutdown coroutines await work. It cannot
    terminate a filesystem call that is already executing in a Python thread;
    process-level bounds remain the responsibility of the deployment supervisor.
    """

    expires_at_monotonic: float
    _clock: Callable[[], float] = field(repr=False, compare=False)

    @classmethod
    def after(
        cls,
        timeout: float,
        *,
        clock: Callable[[], float] | None = None,
    ) -> ShutdownDeadline:
        bounded_timeout = max(0.0, float(timeout))
        resolved_clock = clock or asyncio.get_running_loop().time
        return cls(
            expires_at_monotonic=resolved_clock() + bounded_timeout,
            _clock=resolved_clock,
        )

    def remaining(self) -> float:
        return max(0.0, self.expires_at_monotonic - self._clock())

    @property
    def expired(self) -> bool:
        return self.remaining() <= 0.0

    async def wait(
        self,
        tasks: Iterable[asyncio.Task[_T]],
    ) -> tuple[set[asyncio.Task[_T]], set[asyncio.Task[_T]]]:
        task_set = set(tasks)
        pending_input = {task for task in task_set if not task.done()}
        already_done = task_set - pending_input
        if not pending_input or self.expired:
            return already_done, pending_input
        done, pending = await asyncio.wait(
            pending_input,
            timeout=self.remaining(),
        )
        return already_done | done, pending


__all__ = ["ShutdownDeadline", "consume_task_result"]
