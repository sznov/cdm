from __future__ import annotations

from copy import deepcopy
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal


RUN_RELATIVE_PATH_REFERENCE_MODE = "run_relative_v1"
RunPathReferenceMode = Literal["run_relative_v1"]


class RunPathReferenceError(ValueError):
    """Raised when an artifact path does not stay beneath its declared run."""


def _relative_parts(reference: str) -> tuple[str, ...]:
    if (
        not reference
        or reference != reference.strip()
        or "\\" in reference
        or "\x00" in reference
    ):
        raise RunPathReferenceError("Run path reference is not canonical.")
    windows = PureWindowsPath(reference)
    posix = PurePosixPath(reference)
    raw_parts = reference.split("/")
    if (
        windows.drive
        or windows.root
        or posix.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or any(":" in part for part in raw_parts)
        or posix.as_posix() != reference
    ):
        raise RunPathReferenceError("Run path reference must be a safe relative path.")
    return tuple(raw_parts)


def run_relative_reference(run_dir: Path, target: str | Path) -> str:
    """Encode a filesystem target as a canonical reference beneath ``run_dir``."""

    root = run_dir.resolve()
    candidate = Path(target)
    if not candidate.is_absolute():
        cwd_candidate = candidate.resolve()
        try:
            cwd_candidate.relative_to(root)
        except ValueError:
            candidate = root / candidate
        else:
            candidate = cwd_candidate
    try:
        relative = candidate.resolve().relative_to(root)
    except (OSError, ValueError) as exc:
        raise RunPathReferenceError(
            "Artifact path resolves outside its run directory."
        ) from exc
    reference = relative.as_posix()
    _relative_parts(reference)
    return reference


def resolve_run_reference(
    run_dir: Path,
    reference: str,
    *,
    mode: RunPathReferenceMode | None,
) -> Path:
    """Resolve a current or legacy reference without permitting path escape."""

    root = run_dir.resolve()
    if mode == RUN_RELATIVE_PATH_REFERENCE_MODE:
        candidate = root.joinpath(*_relative_parts(reference))
    elif mode is None:
        if not isinstance(reference, str) or not reference:
            raise RunPathReferenceError("Legacy run path reference is empty.")
        foreign_windows_path = PureWindowsPath(reference)
        candidate_path = Path(reference)
        if foreign_windows_path.is_absolute() and not candidate_path.is_absolute():
            raise RunPathReferenceError(
                "Legacy absolute path cannot be resolved on this platform."
            )
        candidate = candidate_path if candidate_path.is_absolute() else root / candidate_path
    else:
        raise RunPathReferenceError("Run path reference mode is unsupported.")

    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RunPathReferenceError(
            "Artifact path resolves outside its run directory."
        ) from exc
    return resolved


def normalize_web_run_path_references(value: Any, *, run_dir: Path) -> Any:
    """Detach a web-run payload and convert every artifact path to run-relative."""

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            if (
                isinstance(item, str)
                and item
                and (
                    key == "path"
                    or key.endswith("_path")
                    or key.endswith("_dir")
                )
            ):
                normalized[key] = run_relative_reference(run_dir, item)
            else:
                normalized[key] = normalize_web_run_path_references(
                    item,
                    run_dir=run_dir,
                )
        return normalized
    if isinstance(value, list):
        return [
            normalize_web_run_path_references(item, run_dir=run_dir)
            for item in value
        ]
    if isinstance(value, tuple):
        return [
            normalize_web_run_path_references(item, run_dir=run_dir)
            for item in value
        ]
    return deepcopy(value)


def validate_recorded_run_path_references(
    value: Any,
    *,
    run_dir: Path,
    mode: RunPathReferenceMode | None,
    excluded_keys: frozenset[str] = frozenset(),
) -> None:
    """Validate persisted path-shaped fields without changing their spelling."""

    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key)
            if key in excluded_keys:
                continue
            if (
                isinstance(item, str)
                and item
                and (
                    key == "path"
                    or key.endswith("_path")
                    or key.endswith("_dir")
                )
            ):
                resolve_run_reference(run_dir, item, mode=mode)
            else:
                validate_recorded_run_path_references(
                    item,
                    run_dir=run_dir,
                    mode=mode,
                    excluded_keys=excluded_keys,
                )
    elif isinstance(value, (list, tuple)):
        for item in value:
            validate_recorded_run_path_references(
                item,
                run_dir=run_dir,
                mode=mode,
                excluded_keys=excluded_keys,
            )


def validate_relative_reference(reference: str) -> str:
    """Validate and return a canonical v1 reference for typed record boundaries."""

    _relative_parts(reference)
    return reference


__all__ = [
    "RUN_RELATIVE_PATH_REFERENCE_MODE",
    "RunPathReferenceError",
    "RunPathReferenceMode",
    "normalize_web_run_path_references",
    "resolve_run_reference",
    "run_relative_reference",
    "validate_recorded_run_path_references",
    "validate_relative_reference",
]
