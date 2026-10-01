from __future__ import annotations

from typing import Any


RUN_RECORD_SCHEMA_VERSION = 3
SESSION_RECORD_SCHEMA_VERSION = 3
RESULT_RECORD_SCHEMA_VERSION = 2

SCHEMA_VERSION_FIELD = "schema_version"
ARTIFACT_KIND_FIELD = "artifact_kind"


class ArtifactVersionError(ValueError):
    """Raised when an application artifact is not readable by this release."""


def _with_artifact_metadata(payload: dict[str, Any], *, kind: str, version: int) -> dict[str, Any]:
    normalized = dict(payload)
    normalized[ARTIFACT_KIND_FIELD] = kind
    normalized[SCHEMA_VERSION_FIELD] = version
    return normalized


def _require_artifact_metadata(payload: dict[str, Any], *, kind: str, version: int) -> dict[str, Any]:
    actual_kind = payload.get(ARTIFACT_KIND_FIELD)
    actual_version = payload.get(SCHEMA_VERSION_FIELD)
    if actual_kind != kind:
        raise ArtifactVersionError(
            f"Expected {kind!r} artifact, found {actual_kind!r}."
        )
    if actual_version != version:
        raise ArtifactVersionError(
            f"Unsupported {kind} schema version {actual_version!r}; expected {version}."
        )
    return dict(payload)


def add_run_record_version(record: dict[str, Any]) -> dict[str, Any]:
    return _with_artifact_metadata(record, kind="run", version=RUN_RECORD_SCHEMA_VERSION)


def add_session_record_version(record: dict[str, Any]) -> dict[str, Any]:
    return _with_artifact_metadata(record, kind="session", version=SESSION_RECORD_SCHEMA_VERSION)


def add_result_record_version(payload: dict[str, Any]) -> dict[str, Any]:
    return _with_artifact_metadata(payload, kind="result", version=RESULT_RECORD_SCHEMA_VERSION)


def normalize_run_record(record: dict[str, Any]) -> dict[str, Any]:
    return _require_artifact_metadata(record, kind="run", version=RUN_RECORD_SCHEMA_VERSION)


def normalize_session_record(record: dict[str, Any]) -> dict[str, Any]:
    return _require_artifact_metadata(record, kind="session", version=SESSION_RECORD_SCHEMA_VERSION)


def normalize_result_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _require_artifact_metadata(payload, kind="result", version=RESULT_RECORD_SCHEMA_VERSION)


__all__ = [
    "ARTIFACT_KIND_FIELD",
    "ArtifactVersionError",
    "RESULT_RECORD_SCHEMA_VERSION",
    "RUN_RECORD_SCHEMA_VERSION",
    "SCHEMA_VERSION_FIELD",
    "SESSION_RECORD_SCHEMA_VERSION",
    "add_result_record_version",
    "add_run_record_version",
    "add_session_record_version",
    "normalize_result_payload",
    "normalize_run_record",
    "normalize_session_record",
]
