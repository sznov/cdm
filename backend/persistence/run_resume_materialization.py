from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


MATERIALIZED_RESUME_CHECKPOINT_MODE = "materialized_v1"
MATERIALIZED_RESUME_CHECKPOINT_REFERENCE = "checkpoints/resume-source.json"
MATERIALIZED_RESUME_CHECKPOINT_SCHEMA_VERSION = 1


class MaterializedResumeCheckpointError(ValueError):
    """Raised when a detached resume checkpoint is not exact and self-contained."""


class MaterializedResumeCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_kind: Literal["materialized_resume_checkpoint"]
    schema_version: Literal[1]
    source_job_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    source_stage: str = Field(min_length=1)
    source_trace_index: int | None = Field(default=None, ge=0)
    materialized_at_utc: str = Field(min_length=1)
    payload: dict[str, Any]


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def checkpoint_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def materialized_resume_checkpoint_bytes(
    *,
    source_job_id: str,
    source_stage: str,
    source_trace_index: int | None,
    materialized_at_utc: str,
    payload: dict[str, Any],
) -> bytes:
    checkpoint = MaterializedResumeCheckpoint(
        artifact_kind="materialized_resume_checkpoint",
        schema_version=MATERIALIZED_RESUME_CHECKPOINT_SCHEMA_VERSION,
        source_job_id=source_job_id,
        source_stage=source_stage,
        source_trace_index=source_trace_index,
        materialized_at_utc=materialized_at_utc,
        payload=payload,
    )
    return canonical_json_bytes(checkpoint.model_dump(mode="json"))


def parse_materialized_resume_checkpoint(
    payload: bytes,
) -> dict[str, Any]:
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(decoded)
        checkpoint = MaterializedResumeCheckpoint.model_validate(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise MaterializedResumeCheckpointError(
            "Materialized resume checkpoint is invalid."
        ) from exc
    canonical = canonical_json_bytes(checkpoint.model_dump(mode="json"))
    if canonical != payload:
        raise MaterializedResumeCheckpointError(
            "Materialized resume checkpoint is not canonically encoded."
        )
    return checkpoint.model_dump(mode="json")


def read_materialized_resume_checkpoint(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise MaterializedResumeCheckpointError(
            "Materialized resume checkpoint could not be read."
        ) from exc
    return parse_materialized_resume_checkpoint(payload), payload


__all__ = [
    "MATERIALIZED_RESUME_CHECKPOINT_MODE",
    "MATERIALIZED_RESUME_CHECKPOINT_REFERENCE",
    "MATERIALIZED_RESUME_CHECKPOINT_SCHEMA_VERSION",
    "MaterializedResumeCheckpoint",
    "MaterializedResumeCheckpointError",
    "canonical_json_bytes",
    "checkpoint_sha256",
    "materialized_resume_checkpoint_bytes",
    "parse_materialized_resume_checkpoint",
    "read_materialized_resume_checkpoint",
]
