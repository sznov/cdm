from __future__ import annotations

import os
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from core.atomic_io import (
    synchronize_directory,
    synchronized_rmdir,
    synchronized_unlink,
)


_WINDOWS_REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


class StoreTopologyError(RuntimeError):
    """Raised before application-store maintenance could follow an unsafe entry."""


@dataclass(frozen=True, slots=True)
class StoreEntry:
    path: Path
    stat_result: os.stat_result

    @property
    def is_reparse(self) -> bool:
        return stat.S_ISLNK(self.stat_result.st_mode) or bool(
            getattr(self.stat_result, "st_file_attributes", 0)
            & _WINDOWS_REPARSE_ATTRIBUTE
        )

    @property
    def is_directory(self) -> bool:
        return stat.S_ISDIR(self.stat_result.st_mode)

    @property
    def is_regular_file(self) -> bool:
        return stat.S_ISREG(self.stat_result.st_mode)


def entry_exists(path: Path) -> bool:
    """Return link-aware existence without following the final component."""

    return os.path.lexists(path)


def inspect_entry(path: Path) -> StoreEntry | None:
    try:
        result = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise StoreTopologyError(
            f"Application-store entry could not be inspected: {path.name!r}."
        ) from exc
    return StoreEntry(path=path, stat_result=result)


def require_real_directory(path: Path, *, label: str) -> None:
    entry = inspect_entry(path)
    if entry is None:
        raise StoreTopologyError(f"{label} is missing.")
    if entry.is_reparse or not entry.is_directory:
        raise StoreTopologyError(f"{label} must be a real local directory.")


def require_safe_mutable_file(
    path: Path,
    *,
    allow_missing: bool = False,
    label: str = "Mutable application-store file",
) -> None:
    entry = inspect_entry(path)
    if entry is None:
        if allow_missing:
            return
        raise StoreTopologyError(f"{label} is missing.")
    if (
        entry.is_reparse
        or not entry.is_regular_file
        or int(getattr(entry.stat_result, "st_nlink", 1)) != 1
    ):
        raise StoreTopologyError(
            f"{label} must be a non-linked regular file."
        )


def ensure_real_directory_chain(root: Path, destination: Path) -> None:
    """Create *destination* beneath *root* without traversing linked components."""

    require_real_directory(root, label="Application data root")
    try:
        relative = destination.relative_to(root)
    except ValueError as exc:
        raise StoreTopologyError(
            "Application-store directory escapes its configured root."
        ) from exc
    current = root
    for component in relative.parts:
        current = current / component
        entry = inspect_entry(current)
        if entry is None:
            try:
                current.mkdir()
                synchronize_directory(current.parent)
            except FileExistsError:
                # Another in-process creator may have published this exact
                # directory after our non-following inspection.
                pass
            except OSError as exc:
                raise StoreTopologyError(
                    f"Application-store directory could not be created: {component!r}."
                ) from exc
            entry = inspect_entry(current)
        if entry is None or entry.is_reparse or not entry.is_directory:
            raise StoreTopologyError(
                f"Application-store directory component is unsafe: {component!r}."
            )


def ensure_real_directory_path(destination: Path) -> None:
    """Create an absolute directory path while rejecting linked ancestors."""

    absolute = Path(os.path.abspath(destination))
    missing_or_existing: list[Path] = []
    current = absolute
    while current.parent != current:
        missing_or_existing.append(current)
        current = current.parent
    require_real_directory(current, label="Filesystem root")
    for component in reversed(missing_or_existing):
        entry = inspect_entry(component)
        if entry is None:
            try:
                component.mkdir()
                synchronize_directory(component.parent)
            except FileExistsError:
                # Concurrent first-run creation is safe only when the winner
                # published the same real directory.
                pass
            except OSError as exc:
                raise StoreTopologyError(
                    f"Application-store directory could not be created: "
                    f"{component.name!r}."
                ) from exc
            entry = inspect_entry(component)
        if entry is None or entry.is_reparse or not entry.is_directory:
            raise StoreTopologyError(
                f"Application-store directory component is unsafe: "
                f"{component.name!r}."
            )


def iter_directory_entries(path: Path) -> Iterator[StoreEntry]:
    require_real_directory(path, label="Application-store directory")
    try:
        with os.scandir(path) as entries:
            snapshots = [
                StoreEntry(
                    path=path / entry.name,
                    # ``DirEntry.stat()`` reports ``st_nlink == 0`` for regular
                    # files on some Windows/Python combinations.  ``lstat()``
                    # preserves the non-following boundary and returns the
                    # usable link count needed for mutable-file checks.
                    stat_result=os.lstat(entry.path),
                )
                for entry in entries
            ]
    except OSError as exc:
        raise StoreTopologyError(
            f"Application-store directory could not be enumerated: {path.name!r}."
        ) from exc
    yield from sorted(snapshots, key=lambda item: item.path.name.casefold())


def first_unsafe_tree_entry(root: Path) -> Path | None:
    """Return the first unsafe mutable entry below one verified real directory."""

    require_real_directory(root, label="Application record family")
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in iter_directory_entries(directory):
            if entry.is_reparse:
                return entry.path
            if entry.is_directory:
                pending.append(entry.path)
            elif (
                entry.is_regular_file
                and (
                    entry.path.name == "trace.jsonl"
                    or entry.path.name == "post-run-transaction.json"
                    or entry.path.name.endswith(".pending")
                )
                and int(getattr(entry.stat_result, "st_nlink", 1)) != 1
            ):
                return entry.path
    return None


def iter_real_files(root: Path) -> Iterator[Path]:
    """Yield files without following any linked directory or file."""

    require_real_directory(root, label="Application-store directory")
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in iter_directory_entries(directory):
            if entry.is_reparse:
                raise StoreTopologyError(
                    f"Application-store tree contains a linked entry: {entry.path.name!r}."
                )
            if entry.is_directory:
                pending.append(entry.path)
            elif entry.is_regular_file:
                yield entry.path


def remove_verified_tree(root: Path) -> None:
    """Remove one real directory tree without following any entry."""

    require_real_directory(root, label="Application record family")
    pending: list[tuple[Path, bool]] = [(root, False)]
    while pending:
        path, visited = pending.pop()
        if visited:
            synchronized_rmdir(path)
            continue
        pending.append((path, True))
        children = list(iter_directory_entries(path))
        for entry in reversed(children):
            if entry.is_reparse:
                raise StoreTopologyError(
                    f"Application record family contains a linked entry: "
                    f"{entry.path.name!r}."
                )
            if entry.is_directory:
                pending.append((entry.path, False))
                continue
            if not entry.is_regular_file:
                raise StoreTopologyError(
                    f"Application record family contains an unsupported entry: "
                    f"{entry.path.name!r}."
                )
            synchronized_unlink(entry.path)


def validate_relative_components(
    root: Path,
    relative: str,
    *,
    allow_final_reparse: bool,
) -> Path:
    """Validate existing components of a recovery path without following them."""

    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(
        part in {"", ".", ".."} for part in pure.parts
    ):
        raise StoreTopologyError("Recovery path is not a safe relative path.")
    require_real_directory(root, label="Application data root")
    current = root
    for index, component in enumerate(pure.parts):
        current = current / component
        entry = inspect_entry(current)
        if entry is None:
            break
        is_final = index == len(pure.parts) - 1
        if entry.is_reparse:
            if allow_final_reparse and is_final:
                return current
            raise StoreTopologyError(
                f"Recovery path contains a linked ancestor: {component!r}."
            )
        if not is_final and not entry.is_directory:
            raise StoreTopologyError(
                f"Recovery path ancestor is not a directory: {component!r}."
            )
    return current


__all__ = [
    "StoreEntry",
    "StoreTopologyError",
    "ensure_real_directory_chain",
    "ensure_real_directory_path",
    "entry_exists",
    "first_unsafe_tree_entry",
    "inspect_entry",
    "iter_directory_entries",
    "iter_real_files",
    "remove_verified_tree",
    "require_real_directory",
    "require_safe_mutable_file",
    "validate_relative_components",
]
