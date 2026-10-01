from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import ContextManager


@dataclass(slots=True)
class _LockEntry:
    lock: threading.RLock
    references: int = 0


class KeyedLockRegistry:
    """Process-local re-entrant locks for artifact transactions."""

    def __init__(self) -> None:
        self._registry_lock = threading.Lock()
        self._entries: dict[tuple[str, str], _LockEntry] = {}

    @property
    def active_entry_count(self) -> int:
        """Return the number of keys currently held or awaited."""

        with self._registry_lock:
            return len(self._entries)

    def _release_reference(
        self,
        registry_key: tuple[str, str],
        entry: _LockEntry,
    ) -> None:
        with self._registry_lock:
            current = self._entries.get(registry_key)
            if current is not entry:
                raise RuntimeError("Keyed lock registry entry changed while in use.")
            entry.references -= 1
            if entry.references < 0:
                raise RuntimeError("Keyed lock registry reference count became negative.")
            if entry.references == 0:
                del self._entries[registry_key]

    @contextmanager
    def hold(self, namespace: str, key: str | Path) -> Iterator[None]:
        normalized_key = (
            os.path.normcase(os.path.abspath(key))
            if isinstance(key, Path)
            else str(key)
        )
        registry_key = (namespace, normalized_key)
        with self._registry_lock:
            entry = self._entries.get(registry_key)
            if entry is None:
                entry = _LockEntry(lock=threading.RLock())
                self._entries[registry_key] = entry
            entry.references += 1
        try:
            entry.lock.acquire()
        except BaseException:
            self._release_reference(registry_key, entry)
            raise
        try:
            yield
        finally:
            entry.lock.release()
            self._release_reference(registry_key, entry)


ARTIFACT_LOCKS = KeyedLockRegistry()
_LOCK_RANKS = {"run": 10, "session": 20}
_LOCK_ORDER_STATE = threading.local()


@contextmanager
def _ranked_artifact_lock(namespace: str, path: Path) -> Iterator[None]:
    rank = _LOCK_RANKS[namespace]
    identity = os.path.normcase(os.path.abspath(path))
    stack: list[tuple[int, str, str]] = getattr(
        _LOCK_ORDER_STATE,
        "stack",
        [],
    )
    reentrant = (rank, namespace, identity) in stack
    if stack and not reentrant:
        previous_rank, previous_namespace, previous_identity = stack[-1]
        if rank < previous_rank:
            raise RuntimeError(
                "Artifact lock order violation: run locks must precede "
                "session locks."
            )
        if (
            rank == previous_rank
            and namespace == previous_namespace
            and identity != previous_identity
            and identity < previous_identity
        ):
            raise RuntimeError(
                f"Artifact lock order violation: {namespace} locks must be "
                "acquired in sorted path order."
            )
    with ARTIFACT_LOCKS.hold(namespace, path):
        stack.append((rank, namespace, identity))
        _LOCK_ORDER_STATE.stack = stack
        try:
            yield
        finally:
            released = stack.pop()
            if released != (rank, namespace, identity):
                raise RuntimeError("Artifact lock stack was released out of order.")
            if not stack:
                try:
                    del _LOCK_ORDER_STATE.stack
                except AttributeError:  # pragma: no cover - defensive
                    pass


def run_lock(run_dir: Path) -> ContextManager[None]:
    return _ranked_artifact_lock("run", run_dir)


@contextmanager
def run_locks(run_dirs: Iterator[Path] | list[Path] | tuple[Path, ...]) -> Iterator[None]:
    ordered = sorted(
        {Path(path) for path in run_dirs},
        key=lambda path: os.path.normcase(os.path.abspath(path)),
    )
    with ExitStack() as stack:
        for run_dir in ordered:
            stack.enter_context(run_lock(run_dir))
        yield


def session_lock(record_path: Path) -> ContextManager[None]:
    return _ranked_artifact_lock("session", record_path)


def cache_lock(cache_path: Path) -> ContextManager[None]:
    return ARTIFACT_LOCKS.hold("cache", cache_path)


__all__ = [
    "ARTIFACT_LOCKS",
    "KeyedLockRegistry",
    "cache_lock",
    "run_lock",
    "run_locks",
    "session_lock",
]
