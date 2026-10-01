from __future__ import annotations

import os
import tempfile
from pathlib import Path


def synchronize_directory(path: Path) -> None:
    """Synchronize one directory where POSIX exposes that operation."""

    if os.name != "posix":
        # Python exposes no portable Windows equivalent to opening and fsyncing
        # a directory handle. The file itself was synchronized before replace.
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def synchronized_mkdir(
    path: Path,
    *,
    parents: bool = False,
    exist_ok: bool = False,
) -> Path:
    """Create a directory and synchronize every newly published parent entry."""

    path = Path(path)
    missing: list[Path] = []
    current = path
    while not current.exists():
        missing.append(current)
        if not parents or current.parent == current:
            break
        current = current.parent
    path.mkdir(parents=parents, exist_ok=exist_ok)
    for created in reversed(missing):
        synchronize_directory(created.parent)
    return path


def synchronized_replace(source: Path, destination: Path) -> None:
    """Atomically replace a path and synchronize both affected directories."""

    source = Path(source)
    destination = Path(destination)
    os.replace(source, destination)
    synchronized: set[str] = set()
    for directory in (destination.parent, source.parent):
        identity = os.path.normcase(os.path.abspath(directory))
        if identity in synchronized:
            continue
        synchronize_directory(directory)
        synchronized.add(identity)


def synchronized_unlink(path: Path, *, missing_ok: bool = False) -> bool:
    """Unlink a path and synchronize the removed directory entry."""

    path = Path(path)
    try:
        path.unlink()
    except FileNotFoundError:
        if missing_ok:
            return False
        raise
    synchronize_directory(path.parent)
    return True


def synchronized_rmdir(path: Path) -> None:
    """Remove an empty directory and synchronize its parent entry."""

    path = Path(path)
    path.rmdir()
    synchronize_directory(path.parent)


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Synchronize complete file contents before atomically replacing *path*.

    The temporary file lives beside the destination so ``os.replace`` remains
    atomic. It is closed before replacement, which is required on Windows.
    POSIX directory metadata is synchronized after publication; Python has no
    equivalent portable directory-sync guarantee on Windows.
    """

    synchronized_mkdir(path.parent, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        synchronized_replace(temporary_path, path)
    except BaseException:
        try:
            synchronized_unlink(temporary_path, missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    """Synchronize exact bytes before atomically replacing *path*."""

    synchronized_mkdir(path.parent, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        synchronized_replace(temporary_path, path)
    except BaseException:
        try:
            synchronized_unlink(temporary_path, missing_ok=True)
        except OSError:
            pass
        raise


__all__ = [
    "atomic_write_bytes",
    "atomic_write_text",
    "synchronize_directory",
    "synchronized_mkdir",
    "synchronized_replace",
    "synchronized_rmdir",
    "synchronized_unlink",
]
