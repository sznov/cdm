from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
    model_serializer,
    model_validator,
)

from core.atomic_io import atomic_write_text


BUILD_IDENTITY_SCHEMA_VERSION = 2
BUILD_IDENTITY_RELATIVE_PATH = Path("build") / "build-identity.json"
BUILD_IDENTITY_PATH_ENV = "CDMAPP_BUILD_IDENTITY_PATH"

BuildMode = Literal["source", "docker"]
GitState = Literal["clean", "dirty", "unavailable"]
PythonTarget = Literal["unlocked_source", "linux_runtime"]

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$")
_SOURCE_TREE_DOMAIN = b"cdmapp-executable-source-tree-v1\0"
_SOURCE_ROOTS = (
    "backend",
    "core",
    "frontend",
    "harnesses",
    "judge",
    "scripts",
    "static",
    "third_party",
)
_SOURCE_TOP_LEVEL_FILES = (
    "Dockerfile",
    "main.py",
    "package.json",
)
_EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".local",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__db__",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "playwright-report",
    "test-results",
    "vendor",
}
_EXCLUDED_FILE_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp"}


def _require_sha256(value: str, *, field_name: str) -> str:
    normalized = value.strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return normalized


def _require_safe_version(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not _VERSION_PATTERN.fullmatch(normalized):
        raise ValueError(f"{field_name} contains unsupported characters")
    return normalized


class FileFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str

    @field_validator("path")
    @classmethod
    def require_safe_relative_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        if (
            not normalized
            or path.is_absolute()
            or ".." in path.parts
            or ":" in normalized
            or normalized.startswith(("/", "~"))
        ):
            raise ValueError("fingerprint paths must be repository-relative")
        return path.as_posix()

    @field_validator("sha256")
    @classmethod
    def require_sha256(cls, value: str) -> str:
        return _require_sha256(value, field_name="sha256")


class SourceBuildIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    git_commit: str | None = None
    git_state: GitState
    tree_sha256: str

    @field_validator("git_commit")
    @classmethod
    def require_commit_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not _GIT_COMMIT_PATTERN.fullmatch(normalized):
            raise ValueError("git_commit must be a hexadecimal commit identifier")
        return normalized

    @field_validator("tree_sha256")
    @classmethod
    def require_tree_sha256(cls, value: str) -> str:
        return _require_sha256(value, field_name="tree_sha256")

    @model_validator(mode="after")
    def require_commit_when_git_is_available(self) -> SourceBuildIdentity:
        if self.git_state != "unavailable" and self.git_commit is None:
            raise ValueError("clean or dirty Git state requires a commit identifier")
        return self


class PythonBuildIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    implementation: str
    version: str
    target: PythonTarget
    lockfile: FileFingerprint | None
    bootstrap_lockfile: FileFingerprint | None

    @field_validator("implementation", "version")
    @classmethod
    def require_safe_identity(cls, value: str, info: Any) -> str:
        return _require_safe_version(value, field_name=info.field_name)

    @model_validator(mode="after")
    def require_target_locks(self) -> PythonBuildIdentity:
        if self.target == "unlocked_source":
            if self.lockfile is not None or self.bootstrap_lockfile is not None:
                raise ValueError("unlocked source mode cannot claim a dependency lock")
        elif self.target == "linux_runtime":
            if self.lockfile is None or self.lockfile.path != "requirements-linux.lock":
                raise ValueError("Linux runtime identity requires requirements-linux.lock")
            if self.bootstrap_lockfile is not None:
                raise ValueError("Linux runtime identity has no separate bootstrap lock")
        return self


class NodeBuildIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    npm_version: str
    package_lock: FileFingerprint

    @field_validator("version", "npm_version")
    @classmethod
    def require_safe_version(cls, value: str, info: Any) -> str:
        return _require_safe_version(value, field_name=info.field_name)


class SourceRendererIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: Literal["static/vendor/viz.js"] = "static/vendor/viz.js"
    status: Literal["present", "missing"]
    sha256: str | None

    @field_validator("sha256")
    @classmethod
    def require_optional_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_sha256(value, field_name="source renderer sha256")

    @model_validator(mode="after")
    def require_status_consistency(self) -> SourceRendererIdentity:
        if self.status == "present" and self.sha256 is None:
            raise ValueError("A present source renderer requires its exact SHA-256.")
        if self.status == "missing" and self.sha256 is not None:
            raise ValueError("A missing source renderer cannot report a SHA-256.")
        return self


class FrontendBuildIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_manifest_sha256: str | None
    dist_tree_sha256: str | None
    source_renderer: SourceRendererIdentity | None = None

    @field_validator("asset_manifest_sha256", "dist_tree_sha256")
    @classmethod
    def require_optional_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_sha256(value, field_name="asset_manifest_sha256")


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_identity_sha256(payload: dict[str, Any]) -> str:
    canonical_payload = dict(payload)
    canonical_payload.pop("canonical_sha256", None)
    return hashlib.sha256(_canonical_json_bytes(canonical_payload)).hexdigest()


class BuildIdentity(BaseModel):
    """Secret-free, deterministic identity of one executable application build."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1, 2] = BUILD_IDENTITY_SCHEMA_VERSION
    build_mode: BuildMode
    source: SourceBuildIdentity
    python: PythonBuildIdentity
    node: NodeBuildIdentity
    frontend: FrontendBuildIdentity
    canonical_sha256: str

    @field_validator("canonical_sha256")
    @classmethod
    def require_canonical_sha256(cls, value: str) -> str:
        return _require_sha256(value, field_name="canonical_sha256")

    @model_validator(mode="after")
    def require_self_consistent_identity(self) -> BuildIdentity:
        if self.schema_version == 1:
            if self.frontend.source_renderer is not None:
                raise ValueError(
                    "build identity schema v1 cannot report a source renderer"
                )
        elif self.build_mode == "source":
            if self.frontend.source_renderer is None:
                raise ValueError(
                    "source build identity v2 requires source renderer state"
                )
        elif self.frontend.source_renderer is not None:
            raise ValueError(
                "packaged builds rely on bundled frontend hashes, not a source renderer"
            )
        if self.build_mode == "source":
            if (
                self.frontend.asset_manifest_sha256 is not None
                or self.frontend.dist_tree_sha256 is not None
            ):
                raise ValueError("source builds cannot claim packaged frontend hashes")
        elif (
            self.frontend.asset_manifest_sha256 is None
            or self.frontend.dist_tree_sha256 is None
        ):
            raise ValueError("packaged builds require complete frontend output hashes")
        expected_python_target: PythonTarget = {
            "source": "unlocked_source",
            "docker": "linux_runtime",
        }[self.build_mode]
        if self.python.target != expected_python_target:
            raise ValueError("Python target does not match the build mode")
        payload = self.model_dump(mode="json")
        expected = canonical_identity_sha256(payload)
        if self.canonical_sha256 != expected:
            raise ValueError("canonical_sha256 does not match the build identity payload")
        return self

    @model_serializer(mode="wrap")
    def serialize_identity(self, handler):
        payload = handler(self)
        if self.schema_version == 1:
            frontend = payload.get("frontend")
            if isinstance(frontend, dict):
                frontend.pop("source_renderer", None)
        return payload

    def detached_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_tree_sha256(root: Path) -> str:
    """Hash relative paths and bytes for every regular file in one built tree."""

    resolved = root.resolve()
    if not resolved.is_dir():
        raise RuntimeError(f"Required build directory is missing: {root}")
    files = sorted(
        (path for path in resolved.rglob("*") if path.is_file() and not path.is_symlink()),
        key=lambda path: path.relative_to(resolved).as_posix(),
    )
    if not files:
        raise RuntimeError(f"Required build directory is empty: {root}")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(resolved).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_hash_file(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def _is_excluded_source_path(relative_path: Path) -> bool:
    if any(part in _EXCLUDED_DIRECTORY_NAMES for part in relative_path.parts[:-1]):
        return True
    name = relative_path.name
    if name == ".env" or name.startswith(".env."):
        return True
    return relative_path.suffix.lower() in _EXCLUDED_FILE_SUFFIXES


def executable_source_files(app_root: Path) -> tuple[Path, ...]:
    root = app_root.resolve()
    candidates: list[Path] = []
    for relative_name in _SOURCE_TOP_LEVEL_FILES:
        path = root / relative_name
        if path.is_file() and not path.is_symlink():
            candidates.append(path)
    for relative_root in _SOURCE_ROOTS:
        source_root = root / relative_root
        if not source_root.is_dir() or source_root.is_symlink():
            continue
        for directory, directory_names, file_names in os.walk(source_root, topdown=True):
            current_directory = Path(directory)
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in _EXCLUDED_DIRECTORY_NAMES
                and not (current_directory / name).is_symlink()
            )
            for file_name in sorted(file_names):
                path = current_directory / file_name
                if path.is_symlink():
                    continue
                relative_path = path.relative_to(root)
                if not _is_excluded_source_path(relative_path):
                    candidates.append(path)
    return tuple(sorted(set(candidates), key=lambda path: path.relative_to(root).as_posix()))


def executable_source_tree_sha256(app_root: Path) -> str:
    root = app_root.resolve()
    source_files = executable_source_files(root)
    if not source_files:
        raise RuntimeError(f"No executable source files found below {root}")
    digest = hashlib.sha256()
    digest.update(_SOURCE_TREE_DOMAIN)
    for path in source_files:
        relative_path = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative_path)
        digest.update(b"\0")
        digest.update(bytes.fromhex(_hash_file(path)))
        digest.update(b"\0")
    return digest.hexdigest()


def _run_git(app_root: Path, *arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(app_root), *arguments],
            capture_output=True,
            check=False,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def detect_git_source(app_root: Path) -> tuple[str | None, GitState]:
    commit = _run_git(app_root, "rev-parse", "HEAD")
    if commit is None or not _GIT_COMMIT_PATTERN.fullmatch(commit.lower()):
        return None, "unavailable"
    status = _run_git(app_root, "status", "--porcelain", "--untracked-files=normal", "--", ".")
    if status is None:
        return commit.lower(), "unavailable"
    return commit.lower(), "dirty" if status else "clean"


def _load_declared_node_versions(app_root: Path) -> tuple[str, str]:
    package_path = app_root / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        engines = package["engines"]
        node_version = engines["node"]
        npm_version = engines["npm"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("package.json must declare exact Node and npm build versions") from exc
    if not isinstance(node_version, str) or not isinstance(npm_version, str):
        raise RuntimeError("package.json Node and npm engine values must be strings")
    return (
        _require_safe_version(node_version, field_name="node version"),
        _require_safe_version(npm_version, field_name="npm version"),
    )


def _file_fingerprint(app_root: Path, relative_path: Path) -> dict[str, str]:
    path = app_root / relative_path
    if not path.is_file():
        raise RuntimeError(f"Required build input is missing: {relative_path.as_posix()}")
    return {
        "path": relative_path.as_posix(),
        "sha256": _hash_file(path),
    }


def _source_renderer_identity(app_root: Path) -> dict[str, str | None]:
    relative_path = Path("static") / "vendor" / "viz.js"
    path = app_root / relative_path
    present = path.is_file()
    return {
        "path": relative_path.as_posix(),
        "status": "present" if present else "missing",
        "sha256": _hash_file(path) if present else None,
    }


def create_build_identity(
    app_root: Path,
    *,
    build_mode: BuildMode,
    git_commit: str | None = None,
    git_state: GitState | None = None,
    node_version: str | None = None,
    npm_version: str | None = None,
) -> BuildIdentity:
    root = app_root.resolve()
    detected_commit: str | None = None
    detected_state: GitState = "unavailable"
    if git_state is None or git_commit is None:
        detected_commit, detected_state = detect_git_source(root)
    resolved_commit = git_commit.strip().lower() if git_commit and git_commit.strip() else detected_commit
    resolved_state = git_state or detected_state

    declared_node_version, declared_npm_version = _load_declared_node_versions(root)
    resolved_node_version = node_version or declared_node_version
    resolved_npm_version = npm_version or declared_npm_version
    package_lock_path = Path("package-lock.json")
    asset_manifest_path = root / "frontend" / "dist" / "asset-manifest.json"
    asset_manifest_sha256 = (
        _hash_file(asset_manifest_path)
        if build_mode != "source" and asset_manifest_path.is_file()
        else None
    )
    frontend_dist_sha256 = (
        directory_tree_sha256(asset_manifest_path.parent)
        if build_mode != "source" and asset_manifest_path.is_file()
        else None
    )
    python_target: PythonTarget
    python_lock: dict[str, str] | None
    if build_mode == "source":
        python_target = "unlocked_source"
        python_lock = None
    elif build_mode == "docker":
        python_target = "linux_runtime"
        python_lock = _file_fingerprint(root, Path("requirements-linux.lock"))
    else:
        raise ValueError(f"Unsupported build mode: {build_mode}")

    payload: dict[str, Any] = {
        "schema_version": BUILD_IDENTITY_SCHEMA_VERSION,
        "build_mode": build_mode,
        "source": {
            "git_commit": resolved_commit,
            "git_state": resolved_state,
            "tree_sha256": executable_source_tree_sha256(root),
        },
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "target": python_target,
            "lockfile": python_lock,
            "bootstrap_lockfile": None,
        },
        "node": {
            "version": resolved_node_version,
            "npm_version": resolved_npm_version,
            "package_lock": _file_fingerprint(root, package_lock_path),
        },
        "frontend": {
            "asset_manifest_sha256": asset_manifest_sha256,
            "dist_tree_sha256": frontend_dist_sha256,
            "source_renderer": (
                _source_renderer_identity(root)
                if build_mode == "source"
                else None
            ),
        },
    }
    payload["canonical_sha256"] = canonical_identity_sha256(payload)
    return BuildIdentity.model_validate(payload)


def write_build_identity(path: Path, identity: BuildIdentity) -> None:
    serialized = json.dumps(
        identity.detached_dict(),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )
    atomic_write_text(path, f"{serialized}\n")


def load_build_identity(path: Path) -> BuildIdentity:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load build identity: {path}") from exc
    return BuildIdentity.model_validate(payload)


def _packaged_build_identity_path() -> Path | None:
    configured = os.environ.get(BUILD_IDENTITY_PATH_ENV, "").strip()
    if configured:
        return Path(configured)
    return None


@lru_cache(maxsize=1)
def current_build_identity() -> BuildIdentity:
    """Return one process-stable identity without repeating Git or tree scans."""

    packaged_path = _packaged_build_identity_path()
    if packaged_path is not None:
        return load_build_identity(packaged_path)
    app_root = Path(__file__).resolve().parents[1]
    return create_build_identity(app_root, build_mode="source")


def _parse_args(arguments: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a deterministic CDM app build identity.")
    parser.add_argument("--mode", choices=("source", "docker"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--app-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--git-commit", default=None)
    parser.add_argument("--git-state", choices=("clean", "dirty", "unavailable"), default=None)
    parser.add_argument("--node-version", default=None)
    parser.add_argument("--npm-version", default=None)
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    args = _parse_args(arguments)
    identity = create_build_identity(
        args.app_root,
        build_mode=args.mode,
        git_commit=args.git_commit,
        git_state=args.git_state,
        node_version=args.node_version,
        npm_version=args.npm_version,
    )
    write_build_identity(args.output, identity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BUILD_IDENTITY_PATH_ENV",
    "BUILD_IDENTITY_RELATIVE_PATH",
    "BUILD_IDENTITY_SCHEMA_VERSION",
    "BuildIdentity",
    "BuildMode",
    "FileFingerprint",
    "FrontendBuildIdentity",
    "GitState",
    "NodeBuildIdentity",
    "PythonBuildIdentity",
    "PythonTarget",
    "SourceRendererIdentity",
    "SourceBuildIdentity",
    "canonical_identity_sha256",
    "create_build_identity",
    "current_build_identity",
    "detect_git_source",
    "directory_tree_sha256",
    "executable_source_files",
    "executable_source_tree_sha256",
    "load_build_identity",
    "write_build_identity",
]
