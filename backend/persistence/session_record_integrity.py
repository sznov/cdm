from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from backend.persistence.common import read_json_file
from core.artifact_versions import (
    SESSION_RECORD_SCHEMA_VERSION,
    ArtifactVersionError,
    normalize_session_record,
)
from core.config_safety import (
    UnsafeConfigurationError,
    validate_secret_free_mapping,
)
from core.model_bindings import validate_model_bindings_security
from harnesses.contracts import RuntimeModelBinding


_SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class SessionRecordIntegrityError(RuntimeError):
    """Raised when a canonical session record is missing, damaged, or unsafe."""

    def __init__(
        self,
        reason: str,
        *,
        reason_code: str = "invalid_session_record",
    ) -> None:
        super().__init__(f"Canonical session record integrity check failed: {reason}.")
        self.reason = reason
        self.reason_code = reason_code


class CanonicalSessionRecord(BaseModel):
    """Strict user-owned session core with additive compatibility metadata."""

    model_config = ConfigDict(extra="allow")

    artifact_kind: Literal["session"]
    schema_version: Literal[SESSION_RECORD_SCHEMA_VERSION]
    session_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    title: str = Field(min_length=1, max_length=160)
    title_source: Literal["user", "generated"]
    created_at_utc: str = Field(min_length=1)
    updated_at_utc: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    provider_label: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_bindings: dict[str, RuntimeModelBinding]
    runtime_harness_id: str = Field(min_length=1)
    harness_definition_revision: str = Field(min_length=1)
    runtime_harness_name: str = Field(min_length=1)
    harness_runtime_config: dict[str, Any]
    specification: str = Field(min_length=1)
    job_ids: list[str] = Field(default_factory=list)
    chat_messages: list[dict[str, Any]] = Field(default_factory=list)
    decision_comments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("job_ids")
    @classmethod
    def validate_rebuildable_job_index(cls, values: list[str]) -> list[str]:
        for value in values:
            if not _SAFE_SESSION_ID.fullmatch(value):
                raise ValueError("job_ids contains an unsafe identifier")
        # Duplicates and stale/incomplete membership are repairable. Preserve
        # the input here so startup can detect and rebuild it from run truth.
        return values

    @model_validator(mode="after")
    def require_consistent_binding_identity(self) -> CanonicalSessionRecord:
        binding = self.model_bindings.get("default")
        if binding is None:
            raise ValueError("model_bindings.default is required")
        if len(self.model_bindings) != 1:
            raise ValueError("only the default model-binding slot is supported")
        if binding.provider != self.provider or binding.model != self.model:
            raise ValueError("top-level provider/model differs from model_bindings.default")
        return self


def validate_canonical_session_record(record: Any) -> dict[str, Any]:
    """Validate session-owned data without consulting the current catalog."""

    if not isinstance(record, dict):
        raise SessionRecordIntegrityError("record root is not a JSON object")
    try:
        normalized = normalize_session_record(record)
    except ArtifactVersionError as exc:
        raise SessionRecordIntegrityError(
            "unsupported or missing artifact metadata",
            reason_code="unsupported_session_record_version",
        ) from exc
    try:
        CanonicalSessionRecord.model_validate(normalized)
        validate_model_bindings_security(normalized.get("model_bindings"))
        validate_secret_free_mapping(
            normalized.get("harness_runtime_config"),
            path="harness_runtime_config",
        )
    except ValidationError as exc:
        raise SessionRecordIntegrityError(
            "required canonical fields are missing or inconsistent"
        ) from exc
    except (UnsafeConfigurationError, ValueError) as exc:
        raise SessionRecordIntegrityError(
            "recorded runtime configuration is unsafe"
        ) from exc
    return dict(normalized)


def validate_canonical_session_record_context(
    record: dict[str, Any],
    *,
    record_path: Path,
    sessions_dir: Path | None,
) -> None:
    session_dir = Path(record_path).parent.resolve()
    directory_session_id = session_dir.name
    if not _SAFE_SESSION_ID.fullmatch(directory_session_id):
        raise SessionRecordIntegrityError("session directory name is invalid")
    if str(record.get("session_id") or "") != directory_session_id:
        raise SessionRecordIntegrityError(
            "record session identity differs from its directory"
        )
    if sessions_dir is None:
        return
    try:
        session_dir.relative_to(Path(sessions_dir).resolve())
    except ValueError as exc:
        raise SessionRecordIntegrityError(
            "session directory is outside the configured store"
        ) from exc


def read_canonical_session_record(
    record_path: Path,
    *,
    sessions_dir: Path | None = None,
) -> dict[str, Any]:
    path = Path(record_path)
    try:
        payload = read_json_file(path)
    except FileNotFoundError as exc:
        raise SessionRecordIntegrityError("canonical record is missing") from exc
    except UnicodeDecodeError as exc:
        raise SessionRecordIntegrityError(
            "canonical record is not valid UTF-8"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SessionRecordIntegrityError(
            "canonical record contains malformed JSON"
        ) from exc
    except OSError as exc:
        raise SessionRecordIntegrityError(
            "canonical record could not be read"
        ) from exc
    record = validate_canonical_session_record(payload)
    validate_canonical_session_record_context(
        record,
        record_path=path,
        sessions_dir=sessions_dir,
    )
    return record


__all__ = [
    "CanonicalSessionRecord",
    "SessionRecordIntegrityError",
    "read_canonical_session_record",
    "validate_canonical_session_record",
    "validate_canonical_session_record_context",
]
