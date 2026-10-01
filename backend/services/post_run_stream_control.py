from __future__ import annotations

import asyncio
from dataclasses import dataclass

from backend.services.run_operation_registry import (
    OperationCancellationResult,
    RunOperationHandle,
)
from backend.services.shutdown_deadline import consume_task_result


@dataclass(frozen=True, slots=True)
class PostRunDisconnectResult:
    operation_bound: bool
    cancellation: OperationCancellationResult | None
    join_worker: bool


class PostRunStreamControl:
    """Connect request-owned delivery loss to operation-owned cancellation.

    The control may observe a disconnect before the operation claim is bound.
    Binding consumes that pending intent before the caller can begin any
    provider or persistence side effect.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._operation_handle: RunOperationHandle | None = None
        self._disconnect_requested = False
        self._cancel_task: asyncio.Task[OperationCancellationResult] | None = (
            None
        )

    @property
    def delivery_detached(self) -> bool:
        return self._disconnect_requested

    async def bind(self, handle: RunOperationHandle) -> None:
        cancel_task: asyncio.Task[OperationCancellationResult] | None
        async with self._lock:
            current = self._operation_handle
            if current is not None and current.operation_id != handle.operation_id:
                raise RuntimeError(
                    "Post-run stream control is already bound to another operation."
                )
            self._operation_handle = handle
            cancel_task = self._ensure_cancel_task_locked()
        if cancel_task is not None:
            await asyncio.shield(cancel_task)

    async def disconnect(self) -> PostRunDisconnectResult:
        return await self._request_delivery_detach()

    async def delivery_failed(self) -> PostRunDisconnectResult:
        return await self._request_delivery_detach()

    async def _request_delivery_detach(self) -> PostRunDisconnectResult:
        async with self._lock:
            self._disconnect_requested = True
            operation_bound = self._operation_handle is not None
            cancel_task = self._ensure_cancel_task_locked()
        cancellation = (
            await asyncio.shield(cancel_task)
            if cancel_task is not None
            else None
        )
        return PostRunDisconnectResult(
            operation_bound=operation_bound,
            cancellation=cancellation,
            join_worker=self._should_join_worker(cancellation),
        )

    def _ensure_cancel_task_locked(
        self,
    ) -> asyncio.Task[OperationCancellationResult] | None:
        handle = self._operation_handle
        if (
            not self._disconnect_requested
            or handle is None
        ):
            return None
        current = self._cancel_task
        if current is None:
            current = asyncio.create_task(
                handle.request_cancel(),
                name=f"post-run-stream-cancel:{handle.operation_id}",
            )
            current.add_done_callback(consume_task_result)
            self._cancel_task = current
        return current

    @staticmethod
    def _should_join_worker(
        cancellation: OperationCancellationResult | None,
    ) -> bool:
        if cancellation is None:
            return False
        if cancellation.already_completed:
            return True
        return (
            cancellation.cancellation_requested
            and cancellation.state == "cancelling"
        )


__all__ = ["PostRunDisconnectResult", "PostRunStreamControl"]
