from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import AsyncIterator, Callable

from backend.services.shutdown_deadline import ShutdownDeadline, consume_task_result


DEFAULT_CONTROL_LEASE_SECONDS = 30.0


class RunOperationKind(StrEnum):
    GENERATION = "generation"
    QUESTION = "question"
    CORRECTION = "correction"
    CORRECTION_SEQUENCE = "correction_sequence"
    DECISION = "decision"


class InternalOperationKind(StrEnum):
    SESSION_DELETE = "session_delete"


class RunOperationState(StrEnum):
    PREPARING = "preparing"
    RUNNING = "running"
    CANCELLING = "cancelling"
    DRAINING = "draining"
    FINALIZING = "finalizing"


class RunOperationCancellationPolicy(StrEnum):
    CANCEL_PROVIDER = "cancel_provider"
    DRAIN_TRANSACTION = "drain_transaction"


_PROVIDER_BACKED_KINDS = frozenset(
    {
        RunOperationKind.GENERATION,
        RunOperationKind.QUESTION,
        RunOperationKind.CORRECTION,
        RunOperationKind.CORRECTION_SEQUENCE,
    }
)


class RunOperationRegistryError(RuntimeError):
    pass


class RunOperationRegistryClosedError(RunOperationRegistryError):
    pass


class RunOperationAdmissionPausedError(RunOperationRegistryClosedError):
    pass


class RunOperationLeaseError(RunOperationRegistryError):
    pass


class RunOperationActivationCancelledError(RunOperationRegistryError):
    pass


class RunOperationConflictError(RunOperationRegistryError):
    def __init__(
        self,
        *,
        session_id: str | None,
        run_id: str | None,
        active_kind: str,
        active_run_id: str | None,
    ) -> None:
        self.session_id = session_id
        self.run_id = run_id
        self.active_kind = active_kind
        self.active_run_id = active_run_id
        target = f"Session {session_id!r}" if session_id else f"Run {run_id!r}"
        detail = f"{target} already owns an active {active_kind} operation"
        if active_run_id:
            detail += f" ({active_run_id})"
        super().__init__(detail + ".")


@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    operation_id: str
    kind: str
    run_id: str | None
    session_id: str | None
    state: str
    provider_backed: bool

    def as_dict(self) -> dict[str, str | bool | None]:
        return {
            "operation_id": self.operation_id,
            "kind": self.kind,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "state": self.state,
            "provider_backed": self.provider_backed,
        }


@dataclass(frozen=True, slots=True)
class AdmissionLeaseSnapshot:
    acquisition_generation: int
    acquired_at_utc: str
    expires_at_utc: str
    active_operations: tuple[OperationSnapshot, ...]


@dataclass(frozen=True, slots=True)
class AdmissionResumeResult:
    resumed: bool
    already_expired: bool


@dataclass(frozen=True, slots=True)
class OperationCancellationResult:
    operation_id: str
    cancellation_requested: bool
    state: str
    already_completed: bool = False
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OperationShutdownResult:
    cancellation_requested_operation_ids: tuple[str, ...]
    unfinished_operation_ids: tuple[str, ...]


@dataclass(slots=True)
class _OperationEntry:
    operation_id: str
    kind: RunOperationKind | InternalOperationKind
    run_id: str | None
    session_id: str | None
    state: RunOperationState
    owner_task: asyncio.Task[object] | None
    task: asyncio.Task[object] | None = None
    depth: int = 1
    cancellation_requested: bool = False
    finished: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def provider_backed(self) -> bool:
        return self.kind in _PROVIDER_BACKED_KINDS

    @property
    def cancellation_policy(self) -> RunOperationCancellationPolicy:
        if self.kind in {RunOperationKind.DECISION, InternalOperationKind.SESSION_DELETE}:
            return RunOperationCancellationPolicy.DRAIN_TRANSACTION
        return RunOperationCancellationPolicy.CANCEL_PROVIDER

    def snapshot(self) -> OperationSnapshot:
        return OperationSnapshot(
            operation_id=self.operation_id,
            kind=str(self.kind),
            run_id=self.run_id,
            session_id=self.session_id,
            state=str(self.state),
            provider_backed=self.provider_backed,
        )


@dataclass(slots=True)
class _AdmissionLease:
    digest: bytes
    acquisition_generation: int
    acquired_at_utc: str
    expires_at_utc: str
    expires_at_monotonic: float


class RunOperationHandle:
    """Narrow ownership handle for one in-memory application operation."""

    __slots__ = ("_registry", "_entry")

    def __init__(
        self,
        registry: RunOperationRegistry,
        entry: _OperationEntry,
    ) -> None:
        self._registry = registry
        self._entry = entry

    @property
    def operation_id(self) -> str:
        return self._entry.operation_id

    @property
    def kind(self) -> str:
        return str(self._entry.kind)

    @property
    def run_id(self) -> str | None:
        return self._entry.run_id

    @property
    def session_id(self) -> str | None:
        return self._entry.session_id

    @property
    def state(self) -> str:
        return str(self._entry.state)

    @property
    def provider_backed(self) -> bool:
        return self._entry.provider_backed

    @property
    def cancellation_policy(self) -> RunOperationCancellationPolicy:
        return self._entry.cancellation_policy

    @property
    def cancellation_requested(self) -> bool:
        return self._entry.cancellation_requested

    async def activate_generation(
        self,
        *,
        run_id: str,
        task: asyncio.Task[object],
    ) -> None:
        await self._registry.activate_generation(self, run_id=run_id, task=task)

    async def finish(self) -> None:
        await self._registry.finish(self)

    async def request_cancel(self) -> OperationCancellationResult:
        return await self._registry.request_cancel(self.operation_id)

    async def begin_draining(self) -> bool:
        return await self._registry.begin_draining(self)

    async def begin_finalizing(self, *, cancellation_handled: bool = False) -> bool:
        return await self._registry.begin_finalizing(
            self,
            cancellation_handled=cancellation_handled,
        )

    async def begin_provider_phase(self) -> bool:
        return await self._registry.begin_provider_phase(self)

    async def wait_finished(self) -> None:
        await self._entry.finished.wait()


_CURRENT_OPERATION: ContextVar[RunOperationHandle | None] = ContextVar(
    "current_run_operation",
    default=None,
)


class RunOperationRegistry:
    """Application-owned admission and in-memory operation authority.

    The registry deliberately owns no persisted lifecycle data. Run records
    remain the canonical lifecycle authority; this object only linearizes
    admission, operation conflicts, and process-local ownership.
    """

    def __init__(
        self,
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
        utc_clock: Callable[[], datetime] | None = None,
        control_lease_seconds: float = DEFAULT_CONTROL_LEASE_SECONDS,
    ) -> None:
        if control_lease_seconds <= 0:
            raise ValueError("Runtime-control lease duration must be positive.")
        self._lock = asyncio.Lock()
        self._accepting = True
        self._monotonic_clock = monotonic_clock
        self._utc_clock = utc_clock or (lambda: datetime.now(timezone.utc))
        self._control_lease_seconds = float(control_lease_seconds)
        self._control_lease: _AdmissionLease | None = None
        self._inactive_lease_digest: bytes | None = None
        self._inactive_lease_expired = False
        self._acquisition_generation = 0
        self._operations: dict[str, _OperationEntry] = {}
        self._run_operations: dict[str, str] = {}
        self._session_generations: dict[str, str] = {}
        self._session_deletions: dict[str, str] = {}

    async def startup(self) -> None:
        async with self._lock:
            self._accepting = True
            self._control_lease = None
            self._inactive_lease_digest = None
            self._inactive_lease_expired = False
            self._acquisition_generation = 0

    async def close_admission(self) -> None:
        async with self._lock:
            self._accepting = False
            self._control_lease = None
            self._inactive_lease_digest = None
            self._inactive_lease_expired = False

    async def begin_shutdown(self) -> tuple[str, ...]:
        """Close admission and synchronously request every safe cancellation."""

        tasks: list[asyncio.Task[object]] = []
        cancellation_requested: list[str] = []
        async with self._lock:
            self._accepting = False
            self._control_lease = None
            self._inactive_lease_digest = None
            self._inactive_lease_expired = False
            for operation_id in tuple(self._operations):
                result, task = self._request_cancel_locked(operation_id)
                if result.cancellation_requested:
                    cancellation_requested.append(operation_id)
                if task is not None and not task.done():
                    tasks.append(task)
        for task in tasks:
            task.cancel()
        return tuple(sorted(cancellation_requested))

    async def shutdown(
        self,
        deadline: ShutdownDeadline,
        *,
        initiate: bool = True,
    ) -> OperationShutdownResult:
        cancellation_requested = (
            await self.begin_shutdown() if initiate else tuple()
        )
        async with self._lock:
            entries = tuple(self._operations.values())
        waiters = [
            asyncio.create_task(
                entry.finished.wait(),
                name=f"operation-shutdown-wait:{entry.operation_id}",
            )
            for entry in entries
        ]
        _done, pending = await deadline.wait(waiters)
        for waiter in pending:
            waiter.cancel()
            waiter.add_done_callback(consume_task_result)
        async with self._lock:
            unfinished = tuple(sorted(self._operations))
        return OperationShutdownResult(
            cancellation_requested_operation_ids=cancellation_requested,
            unfinished_operation_ids=unfinished,
        )

    async def admission_state(self) -> str:
        async with self._lock:
            self._expire_control_lease_locked()
            return self._admission_state_locked()

    async def active_operations(self) -> tuple[OperationSnapshot, ...]:
        async with self._lock:
            self._expire_control_lease_locked()
            return self._snapshots_locked()

    async def generation_run_id(self, session_id: str) -> str | None:
        async with self._lock:
            operation_id = self._session_generations.get(session_id)
            if operation_id is None:
                return None
            entry = self._operations.get(operation_id)
            return None if entry is None else entry.run_id

    async def operation_count(self) -> int:
        async with self._lock:
            return len(self._operations)

    async def pause_control(self, lease: str) -> AdmissionLeaseSnapshot:
        digest = self._lease_digest(lease)
        async with self._lock:
            now = self._monotonic_clock()
            self._expire_control_lease_locked(now)
            if not self._accepting:
                raise RunOperationRegistryClosedError(
                    "Run operation registry is not accepting work."
                )
            current = self._control_lease
            if current is not None:
                if not secrets.compare_digest(current.digest, digest):
                    raise RunOperationLeaseError(
                        "Run admission is controlled by another active lease."
                    )
                self._renew_control_lease_locked(current, now=now)
                return self._lease_snapshot_locked(current)
            self._acquisition_generation += 1
            utc_now = self._utc_now()
            current = _AdmissionLease(
                digest=digest,
                acquisition_generation=self._acquisition_generation,
                acquired_at_utc=self._format_utc(utc_now),
                expires_at_utc=self._format_utc(
                    utc_now + timedelta(seconds=self._control_lease_seconds)
                ),
                expires_at_monotonic=now + self._control_lease_seconds,
            )
            self._control_lease = current
            self._inactive_lease_digest = None
            self._inactive_lease_expired = False
            return self._lease_snapshot_locked(current)

    async def renew_control(self, lease: str) -> AdmissionLeaseSnapshot:
        digest = self._lease_digest(lease)
        async with self._lock:
            now = self._monotonic_clock()
            self._expire_control_lease_locked(now)
            if not self._accepting:
                raise RunOperationRegistryClosedError(
                    "Run operation registry is not accepting work."
                )
            current = self._control_lease
            if current is None or not secrets.compare_digest(current.digest, digest):
                raise RunOperationLeaseError(
                    "Run admission lease is invalid or no longer active."
                )
            self._renew_control_lease_locked(current, now=now)
            return self._lease_snapshot_locked(current)

    async def resume_control(self, lease: str) -> AdmissionResumeResult:
        digest = self._lease_digest(lease)
        async with self._lock:
            self._expire_control_lease_locked()
            if not self._accepting:
                raise RunOperationRegistryClosedError(
                    "Run operation registry is not accepting work."
                )
            current = self._control_lease
            if current is not None:
                if not secrets.compare_digest(current.digest, digest):
                    raise RunOperationLeaseError(
                        "Run admission lease is invalid or no longer active."
                    )
                self._control_lease = None
                self._inactive_lease_digest = digest
                self._inactive_lease_expired = False
                return AdmissionResumeResult(
                    resumed=True,
                    already_expired=False,
                )
            if (
                self._inactive_lease_digest is not None
                and secrets.compare_digest(self._inactive_lease_digest, digest)
            ):
                return AdmissionResumeResult(
                    resumed=False,
                    already_expired=self._inactive_lease_expired,
                )
            # A caller may not know whether a timed-out pause request
            # reached the server. With no active owner, an unknown token is an
            # idempotent no-op; it can never resume another lease.
            return AdmissionResumeResult(
                resumed=False,
                already_expired=False,
            )

    async def health_snapshot(self) -> dict[str, object]:
        async with self._lock:
            self._expire_control_lease_locked()
            current = self._control_lease
            operations = tuple(self._operations.values())
            return {
                "admission": self._admission_state_locked(),
                "admission_generation": (
                    current.acquisition_generation if current is not None else None
                ),
                "admission_expires_at_utc": (
                    current.expires_at_utc if current is not None else None
                ),
                "operation_counts": {
                    "total": len(operations),
                    "provider_backed": sum(
                        1 for entry in operations if entry.provider_backed
                    ),
                    "draining": sum(
                        1
                        for entry in operations
                        if entry.state
                        in {
                            RunOperationState.DRAINING,
                            RunOperationState.FINALIZING,
                        }
                    ),
                },
            }

    async def request_cancel_with_lease(
        self,
        operation_id: str,
        lease: str,
    ) -> OperationCancellationResult:
        digest = self._lease_digest(lease)
        task: asyncio.Task[object] | None = None
        async with self._lock:
            self._expire_control_lease_locked()
            current = self._control_lease
            if current is None or not secrets.compare_digest(current.digest, digest):
                raise RunOperationLeaseError(
                    "Run admission lease is invalid or no longer active."
                )
            result, task = self._request_cancel_locked(operation_id)
        if task is not None and not task.done():
            task.cancel()
        return result

    def _lease_snapshot_locked(
        self,
        lease: _AdmissionLease,
    ) -> AdmissionLeaseSnapshot:
        return AdmissionLeaseSnapshot(
            acquisition_generation=lease.acquisition_generation,
            acquired_at_utc=lease.acquired_at_utc,
            expires_at_utc=lease.expires_at_utc,
            active_operations=self._snapshots_locked(),
        )

    async def claim_generation(self, session_id: str | None) -> RunOperationHandle:
        owner_task = asyncio.current_task()
        if owner_task is None:  # pragma: no cover - application use is task-bound
            raise RuntimeError("Generation admission requires an asyncio task.")
        async with self._lock:
            self._require_admission_locked()
            if session_id:
                conflict_id = self._session_deletions.get(session_id)
                if conflict_id is not None:
                    conflict = self._operations[conflict_id]
                    raise self._conflict(conflict, session_id=session_id)
                conflict_id = self._session_generations.get(session_id)
                if conflict_id is not None:
                    conflict = self._operations[conflict_id]
                    raise self._conflict(conflict, session_id=session_id)
            entry = self._new_entry(
                kind=RunOperationKind.GENERATION,
                run_id=None,
                session_id=session_id,
                state=RunOperationState.PREPARING,
                owner_task=owner_task,
            )
            if session_id:
                self._session_generations[session_id] = entry.operation_id
            return RunOperationHandle(self, entry)

    async def activate_generation(
        self,
        handle: RunOperationHandle,
        *,
        run_id: str,
        task: asyncio.Task[object],
    ) -> None:
        async with self._lock:
            entry = self._owned_entry_locked(handle)
            if entry.kind is not RunOperationKind.GENERATION:
                raise RuntimeError("Only generation operations can be activated.")
            if entry.state is RunOperationState.CANCELLING:
                raise RunOperationActivationCancelledError(
                    "Generation was cancelled before worker activation."
                )
            self._require_admission_locked()
            if entry.run_id is not None and entry.run_id != run_id:
                raise RuntimeError("Generation operation is already bound to another run.")
            conflict_id = self._run_operations.get(run_id)
            if conflict_id is not None and conflict_id != entry.operation_id:
                raise self._conflict(self._operations[conflict_id], run_id=run_id)
            entry.run_id = run_id
            entry.task = task
            entry.state = RunOperationState.RUNNING
            self._run_operations[run_id] = entry.operation_id

    async def claim_run_operation(
        self,
        run_id: str,
        kind: RunOperationKind,
        *,
        session_id: str | None = None,
    ) -> RunOperationHandle:
        owner_task = asyncio.current_task()
        if owner_task is None:  # pragma: no cover - application use is task-bound
            raise RuntimeError("Run operation ownership requires an asyncio task.")
        async with self._lock:
            self._require_admission_locked()
            conflict_id = self._run_operations.get(run_id)
            if conflict_id is not None:
                conflict = self._operations[conflict_id]
                if conflict.owner_task is owner_task:
                    conflict.depth += 1
                    return RunOperationHandle(self, conflict)
                raise self._conflict(conflict, run_id=run_id, session_id=session_id)
            if session_id:
                deletion_id = self._session_deletions.get(session_id)
                if deletion_id is not None:
                    raise self._conflict(
                        self._operations[deletion_id],
                        run_id=run_id,
                        session_id=session_id,
                    )
            entry = self._new_entry(
                kind=kind,
                run_id=run_id,
                session_id=session_id,
                state=RunOperationState.RUNNING,
                owner_task=owner_task,
            )
            entry.task = owner_task
            self._run_operations[run_id] = entry.operation_id
            return RunOperationHandle(self, entry)

    async def reenter(self, handle: RunOperationHandle) -> RunOperationHandle:
        async with self._lock:
            entry = self._owned_entry_locked(handle)
            entry.depth += 1
            return RunOperationHandle(self, entry)

    async def claim_session_deletion(self, session_id: str) -> RunOperationHandle:
        owner_task = asyncio.current_task()
        if owner_task is None:  # pragma: no cover - application use is task-bound
            raise RuntimeError("Session deletion requires an asyncio task.")
        async with self._lock:
            self._require_admission_locked()
            generation_id = self._session_generations.get(session_id)
            if generation_id is not None:
                raise self._conflict(
                    self._operations[generation_id],
                    session_id=session_id,
                )
            deletion_id = self._session_deletions.get(session_id)
            if deletion_id is not None:
                raise self._conflict(
                    self._operations[deletion_id],
                    session_id=session_id,
                )
            for entry in self._operations.values():
                if entry.session_id == session_id:
                    raise self._conflict(entry, session_id=session_id)
            entry = self._new_entry(
                kind=InternalOperationKind.SESSION_DELETE,
                run_id=None,
                session_id=session_id,
                state=RunOperationState.DRAINING,
                owner_task=owner_task,
            )
            entry.task = owner_task
            self._session_deletions[session_id] = entry.operation_id
            return RunOperationHandle(self, entry)

    async def finish(self, handle: RunOperationHandle) -> None:
        async with self._lock:
            entry = self._operations.get(handle.operation_id)
            if entry is None:
                return
            if entry is not handle._entry:
                raise RuntimeError("Run operation ownership was replaced.")
            entry.depth -= 1
            if entry.depth > 0:
                return
            self._operations.pop(entry.operation_id, None)
            if (
                entry.run_id
                and self._run_operations.get(entry.run_id) == entry.operation_id
            ):
                self._run_operations.pop(entry.run_id, None)
            if (
                entry.session_id
                and self._session_generations.get(entry.session_id) == entry.operation_id
            ):
                self._session_generations.pop(entry.session_id, None)
            if (
                entry.session_id
                and self._session_deletions.get(entry.session_id) == entry.operation_id
            ):
                self._session_deletions.pop(entry.session_id, None)
            entry.finished.set()

    async def request_cancel(
        self,
        operation_id: str,
    ) -> OperationCancellationResult:
        task: asyncio.Task[object] | None = None
        async with self._lock:
            result, task = self._request_cancel_locked(operation_id)
        if task is not None and not task.done():
            task.cancel()
        return result

    async def begin_draining(self, handle: RunOperationHandle) -> bool:
        async with self._lock:
            entry = self._owned_entry_locked(handle)
            if entry.state is RunOperationState.CANCELLING:
                return False
            entry.state = RunOperationState.DRAINING
            return True

    async def begin_provider_phase(self, handle: RunOperationHandle) -> bool:
        async with self._lock:
            entry = self._owned_entry_locked(handle)
            if (
                entry.state is RunOperationState.CANCELLING
                or entry.cancellation_requested
            ):
                entry.state = RunOperationState.CANCELLING
                return False
            if not entry.provider_backed:
                return False
            entry.state = RunOperationState.RUNNING
            return True

    async def begin_finalizing(
        self,
        handle: RunOperationHandle,
        *,
        cancellation_handled: bool = False,
    ) -> bool:
        async with self._lock:
            entry = self._owned_entry_locked(handle)
            if (
                entry.state is RunOperationState.CANCELLING
                and not cancellation_handled
            ):
                return False
            entry.state = RunOperationState.FINALIZING
            return True

    def _new_entry(
        self,
        *,
        kind: RunOperationKind | InternalOperationKind,
        run_id: str | None,
        session_id: str | None,
        state: RunOperationState,
        owner_task: asyncio.Task[object] | None,
    ) -> _OperationEntry:
        operation_id = secrets.token_urlsafe(18)
        while operation_id in self._operations:  # pragma: no cover - defensive
            operation_id = secrets.token_urlsafe(18)
        entry = _OperationEntry(
            operation_id=operation_id,
            kind=kind,
            run_id=run_id,
            session_id=session_id,
            state=state,
            owner_task=owner_task,
            finished=asyncio.Event(),
        )
        self._operations[operation_id] = entry
        return entry

    def _owned_entry_locked(self, handle: RunOperationHandle) -> _OperationEntry:
        entry = self._operations.get(handle.operation_id)
        if entry is None or entry is not handle._entry:
            raise RuntimeError("Run operation is no longer registered.")
        return entry

    def _require_admission_locked(self) -> None:
        self._expire_control_lease_locked()
        if not self._accepting:
            raise RunOperationRegistryClosedError(
                "Run operation registry is not accepting work."
            )
        if self._control_lease is not None:
            raise RunOperationAdmissionPausedError(
                "Run admission is temporarily paused."
            )

    def _admission_state_locked(self) -> str:
        if not self._accepting:
            return "closed"
        if self._control_lease is not None:
            return "paused"
        return "accepting"

    def _request_cancel_locked(
        self,
        operation_id: str,
    ) -> tuple[OperationCancellationResult, asyncio.Task[object] | None]:
        entry = self._operations.get(operation_id)
        if entry is None:
            return (
                OperationCancellationResult(
                    operation_id=operation_id,
                    cancellation_requested=False,
                    state="completed",
                    already_completed=True,
                ),
                None,
            )
        if entry.state is RunOperationState.CANCELLING:
            return (
                OperationCancellationResult(
                    operation_id=operation_id,
                    cancellation_requested=True,
                    state=str(entry.state),
                    reason="cancellation_already_requested",
                ),
                None,
            )
        if (
            entry.cancellation_policy
            is RunOperationCancellationPolicy.DRAIN_TRANSACTION
        ):
            if entry.state is not RunOperationState.FINALIZING:
                entry.state = RunOperationState.DRAINING
            return (
                OperationCancellationResult(
                    operation_id=operation_id,
                    cancellation_requested=False,
                    state=str(entry.state),
                    reason="operation_has_transactional_persistence",
                ),
                None,
            )
        if (
            entry.kind is RunOperationKind.GENERATION
            and entry.state is RunOperationState.FINALIZING
        ):
            entry.cancellation_requested = True
            return (
                OperationCancellationResult(
                    operation_id=operation_id,
                    cancellation_requested=False,
                    state=str(entry.state),
                    reason="operation_has_transactional_persistence",
                ),
                None,
            )
        if entry.state in {
            RunOperationState.DRAINING,
            RunOperationState.FINALIZING,
        }:
            entry.cancellation_requested = True
            return (
                OperationCancellationResult(
                    operation_id=operation_id,
                    cancellation_requested=True,
                    state=str(entry.state),
                    reason="cancellation_deferred_until_safe_boundary",
                ),
                None,
            )
        entry.cancellation_requested = True
        entry.state = RunOperationState.CANCELLING
        return (
            OperationCancellationResult(
                operation_id=operation_id,
                cancellation_requested=True,
                state=str(entry.state),
            ),
            entry.task,
        )

    def _expire_control_lease_locked(self, now: float | None = None) -> None:
        current = self._control_lease
        if current is None:
            return
        monotonic_now = self._monotonic_clock() if now is None else now
        if monotonic_now < current.expires_at_monotonic:
            return
        self._inactive_lease_digest = current.digest
        self._inactive_lease_expired = True
        self._control_lease = None

    def _renew_control_lease_locked(
        self,
        lease: _AdmissionLease,
        *,
        now: float,
    ) -> None:
        utc_now = self._utc_now()
        lease.expires_at_monotonic = now + self._control_lease_seconds
        lease.expires_at_utc = self._format_utc(
            utc_now + timedelta(seconds=self._control_lease_seconds)
        )

    def _utc_now(self) -> datetime:
        value = self._utc_clock()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _format_utc(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _lease_digest(lease: str) -> bytes:
        if not isinstance(lease, str) or not 20 <= len(lease) <= 256:
            raise RunOperationLeaseError(
                "Run admission lease is invalid or no longer active."
            )
        return hashlib.sha256(lease.encode("utf-8")).digest()

    def _snapshots_locked(self) -> tuple[OperationSnapshot, ...]:
        return tuple(
            entry.snapshot()
            for entry in sorted(
                self._operations.values(),
                key=lambda item: (item.session_id or "", item.run_id or "", item.operation_id),
            )
        )

    @staticmethod
    def _conflict(
        entry: _OperationEntry,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> RunOperationConflictError:
        return RunOperationConflictError(
            session_id=session_id or entry.session_id,
            run_id=run_id or entry.run_id,
            active_kind=str(entry.kind),
            active_run_id=entry.run_id,
        )


@asynccontextmanager
async def claim_run_operation(
    run_id: str,
    kind: RunOperationKind,
    *,
    registry: RunOperationRegistry,
    session_id: str | None = None,
) -> AsyncIterator[RunOperationHandle]:
    parent = _CURRENT_OPERATION.get()
    inherited = (
        parent is not None
        and parent._registry is registry
        and parent.run_id == run_id
    )
    handle = (
        await registry.reenter(parent)
        if inherited and parent is not None
        else await registry.claim_run_operation(
            run_id,
            kind,
            session_id=session_id,
        )
    )
    token = None if inherited else _CURRENT_OPERATION.set(handle)
    try:
        yield handle
    finally:
        try:
            await handle.finish()
        finally:
            if token is not None:
                _CURRENT_OPERATION.reset(token)


__all__ = [
    "AdmissionLeaseSnapshot",
    "AdmissionResumeResult",
    "DEFAULT_CONTROL_LEASE_SECONDS",
    "InternalOperationKind",
    "OperationSnapshot",
    "OperationCancellationResult",
    "OperationShutdownResult",
    "RunOperationAdmissionPausedError",
    "RunOperationActivationCancelledError",
    "RunOperationCancellationPolicy",
    "RunOperationConflictError",
    "RunOperationHandle",
    "RunOperationKind",
    "RunOperationLeaseError",
    "RunOperationRegistry",
    "RunOperationRegistryClosedError",
    "RunOperationRegistryError",
    "RunOperationState",
    "claim_run_operation",
]
