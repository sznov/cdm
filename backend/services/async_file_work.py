from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any


async def finish_shielded_task(task: asyncio.Task[Any]) -> Any:
    """Join work that cannot be stopped by cancelling its awaiting coroutine."""

    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
        except BaseException:
            break
    return task.result()


async def run_thread_to_completion(
    function: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run filesystem work off-loop and never orphan it on cancellation."""

    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        try:
            await finish_shielded_task(task)
        except BaseException:
            # Cancellation remains authoritative. Its caller owns any
            # lifecycle repair required after a failed filesystem transaction.
            pass
        raise cancellation


__all__ = ["finish_shielded_task", "run_thread_to_completion"]
