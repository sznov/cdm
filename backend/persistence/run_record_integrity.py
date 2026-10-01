from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.persistence.run_path_references import (
    RUN_RELATIVE_PATH_REFERENCE_MODE,
    RunPathReferenceError,
    resolve_run_reference,
    validate_relative_reference,
)
from backend.persistence.run_resume_materialization import (
    MATERIALIZED_RESUME_CHECKPOINT_MODE,
    MATERIALIZED_RESUME_CHECKPOINT_REFERENCE,
    MaterializedResumeCheckpointError,
    checkpoint_sha256,
    read_materialized_resume_checkpoint,
)
from backend.persistence.store_topology import inspect_entry
from backend.persistence.common import read_json_file
from core.config_safety import UnsafeConfigurationError
from core.model_bindings import validate_model_bindings_security
from core.artifact_versions import (
    RUN_RECORD_SCHEMA_VERSION,
    ArtifactVersionError,
    normalize_run_record,
)
from core.statuses import (
    RUN_STATUS_CANCELLED,
    RUN_STATUS_CANCELLING,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_INTERRUPTED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
)
from harnesses.contracts import EffectiveHarnessRunSpec, RuntimeModelBinding
from harnesses.provenance import RunProvenance, canonical_sha256


RunLifecycleStatus = Literal[
    "queued",
    "running",
    "cancelling",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
]


class RunRecordIntegrityError(RuntimeError):
    """Raised when a canonical run record cannot be safely mutated."""

    def __init__(
        self,
        reason: str,
        *,
        reason_code: str = "invalid_run_record",
    ) -> None:
        super().__init__(f"Canonical run record integrity check failed: {reason}.")
        self.reason = reason
        self.reason_code = reason_code


_SAFE_RECORD_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class CanonicalRunRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str | None
    retry_of_job_id: str | None = None
    resume_from_job_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    resume_trace_index: int | None = Field(default=None, ge=0)
    resume_checkpoint_stage: str | None = None
    resume_checkpoint_mode: Literal["materialized_v1"] | None = None
    resume_checkpoint_path: str | None = None
    resume_checkpoint_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    specification_path: Literal["specification.txt"]
    specification_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    specification_length: int = Field(ge=1)

    @model_validator(mode="after")
    def require_consistent_resume_identity(self) -> CanonicalRunRequest:
        if self.retry_of_job_id and self.resume_from_job_id:
            raise ValueError("retry and resume identities are mutually exclusive")
        resume_values = (
            self.resume_trace_index,
            self.resume_checkpoint_stage,
            self.resume_checkpoint_mode,
            self.resume_checkpoint_path,
            self.resume_checkpoint_sha256,
        )
        if not self.resume_from_job_id:
            if any(value is not None for value in resume_values):
                raise ValueError("fresh runs cannot contain resume checkpoint fields")
            return self
        if not self.resume_checkpoint_stage or not self.resume_checkpoint_path:
            raise ValueError("resumed runs require checkpoint stage and path")
        if self.resume_checkpoint_mode == MATERIALIZED_RESUME_CHECKPOINT_MODE:
            if (
                self.resume_checkpoint_path
                != MATERIALIZED_RESUME_CHECKPOINT_REFERENCE
                or not self.resume_checkpoint_sha256
            ):
                raise ValueError(
                    "materialized resumes require the canonical path and hash"
                )
        elif self.resume_checkpoint_mode is None:
            if self.resume_checkpoint_sha256 is not None:
                raise ValueError("legacy resumes cannot contain a checkpoint hash")
        else:  # pragma: no cover - Literal validation rejects this first
            raise ValueError("resume checkpoint mode is unsupported")
        return self


class CanonicalRunRecord(BaseModel):
    """Strict mutable-record core with additive extension metadata."""

    model_config = ConfigDict(extra="allow")

    artifact_kind: Literal["run"]
    schema_version: Literal[RUN_RECORD_SCHEMA_VERSION]
    job_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    status: RunLifecycleStatus
    queued_at_utc: str | None
    started_at_utc: str | None
    completed_at_utc: str | None
    provider: str = Field(min_length=1)
    provider_label: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_bindings: dict[str, RuntimeModelBinding]
    runtime_harness_id: str = Field(min_length=1)
    harness_definition_revision: str = Field(min_length=1)
    effective_harness_run_spec: EffectiveHarnessRunSpec
    provenance: RunProvenance
    runtime_harness_name: str = Field(min_length=1)
    runtime_endpoint: str = Field(min_length=1)
    session_id: str | None
    agent_graph: dict[str, Any]
    path_reference_mode: Literal["run_relative_v1"] | None = None
    model_call_log_dir: str = Field(min_length=1)
    request: CanonicalRunRequest
    result: dict[str, Any] | None
    error: str | None

    @model_validator(mode="after")
    def require_consistent_sealed_identity(self) -> CanonicalRunRecord:
        if self.path_reference_mode == RUN_RELATIVE_PATH_REFERENCE_MODE:
            validate_relative_reference(self.model_call_log_dir)
            if self.request.resume_checkpoint_path:
                validate_relative_reference(self.request.resume_checkpoint_path)

        binding = self.model_bindings.get("default")
        if binding is None:
            raise ValueError("model_bindings.default is required")
        if len(self.model_bindings) != 1:
            raise ValueError("only the default model-binding slot is supported")
        if binding.provider != self.provider or binding.model != self.model:
            raise ValueError("top-level provider/model differs from model_bindings.default")

        spec = self.effective_harness_run_spec
        if (
            spec.harness_id != self.runtime_harness_id
            or spec.definition_revision != self.harness_definition_revision
        ):
            raise ValueError("recorded harness identity differs from the effective specification")
        if spec.model_bindings.get("default") != binding:
            raise ValueError("recorded model binding differs from the effective specification")

        workflow = self.provenance.workflow
        if (
            workflow.workflow_id != spec.harness_id
            or workflow.definition_revision != spec.definition_revision
            or workflow.executor_id != spec.executor_id
            or workflow.effective_spec_sha256 != canonical_sha256(spec)
        ):
            raise ValueError("run provenance differs from the effective harness specification")
        provider = self.provenance.provider
        if (
            provider.provider_id != binding.provider
            or provider.model_id != binding.model
            or provider.binding_sha256 != canonical_sha256(binding)
        ):
            raise ValueError("run provenance differs from the effective model binding")
        if self.provenance.specification_sha256 != self.request.specification_sha256:
            raise ValueError("request and provenance specification hashes differ")
        if self.request.session_id != self.session_id:
            raise ValueError("request and run session identities differ")

        if self.status == RUN_STATUS_QUEUED and not self.queued_at_utc:
            raise ValueError("queued runs require queued_at_utc")
        if self.status in {RUN_STATUS_RUNNING, RUN_STATUS_CANCELLING} and not (
            self.started_at_utc or self.queued_at_utc
        ):
            raise ValueError("active runs require a queued or started timestamp")
        if self.status in {
            RUN_STATUS_COMPLETED,
            RUN_STATUS_FAILED,
            RUN_STATUS_CANCELLED,
            RUN_STATUS_INTERRUPTED,
        } and not self.completed_at_utc:
            raise ValueError("terminal runs require completed_at_utc")
        return self


def validate_canonical_run_record(record: Any) -> dict[str, Any]:
    """Validate the sealed mutable core without rewriting extension values."""

    if not isinstance(record, dict):
        raise RunRecordIntegrityError("record root is not a JSON object")
    try:
        normalized = normalize_run_record(record)
    except ArtifactVersionError as exc:
        raise RunRecordIntegrityError(
            "unsupported or missing artifact metadata",
            reason_code="unsupported_run_record_version",
        ) from exc
    try:
        CanonicalRunRecord.model_validate(normalized)
        validate_model_bindings_security(normalized.get("model_bindings"))
        effective_spec = normalized.get("effective_harness_run_spec")
        if isinstance(effective_spec, dict):
            validate_model_bindings_security(effective_spec.get("model_bindings"))
    except ValidationError as exc:
        errors = exc.errors(include_url=False)
        locations = {
            tuple(str(part) for part in error.get("loc") or ())
            for error in errors
        }
        messages = " ".join(str(error.get("msg") or "") for error in errors).casefold()
        if ("request", "specification_path") in locations:
            raise RunRecordIntegrityError(
                "recorded specification reference is invalid",
                reason_code="invalid_specification_reference",
            ) from exc
        if "path reference" in messages or "safe relative path" in messages:
            raise RunRecordIntegrityError(
                "recorded run path reference is invalid",
                reason_code="invalid_run_path_reference",
            ) from exc
        raise RunRecordIntegrityError(
            "required canonical fields are missing or inconsistent"
        ) from exc
    except (UnsafeConfigurationError, ValueError) as exc:
        raise RunRecordIntegrityError("recorded runtime configuration is unsafe") from exc
    return dict(normalized)


def validate_canonical_run_record_context(
    record: dict[str, Any],
    *,
    record_path: Path,
    runs_dir: Path | None,
) -> None:
    run_dir = Path(record_path.parent)
    directory_job_id = run_dir.name
    if not _SAFE_RECORD_ID.fullmatch(directory_job_id):
        raise RunRecordIntegrityError("run directory name is invalid")
    if str(record.get("job_id") or "") != directory_job_id:
        raise RunRecordIntegrityError("record job identity differs from its directory")
    if runs_dir is None:
        return

    runs_root = Path(runs_dir)
    try:
        Path(run_dir.absolute()).relative_to(Path(runs_root.absolute()))
    except ValueError as exc:
        raise RunRecordIntegrityError("run directory is outside the configured store") from exc

    request = record.get("request")
    if not isinstance(request, dict):
        return
    checkpoint_reference = request.get("resume_checkpoint_path")
    source_job_id = str(request.get("resume_from_job_id") or "").strip()
    if checkpoint_reference in (None, ""):
        return
    if not source_job_id or not _SAFE_RECORD_ID.fullmatch(source_job_id):
        raise RunRecordIntegrityError(
            "resume checkpoint path has no valid source run identity",
            reason_code="invalid_run_path_reference",
        )
    mode = request.get("resume_checkpoint_mode")
    if mode == MATERIALIZED_RESUME_CHECKPOINT_MODE:
        try:
            checkpoint_directory = run_dir / "checkpoints"
            checkpoint_path = (
                checkpoint_directory
                / Path(MATERIALIZED_RESUME_CHECKPOINT_REFERENCE).name
            )
            directory_entry = inspect_entry(checkpoint_directory)
            entry = inspect_entry(checkpoint_path)
            if (
                directory_entry is None
                or directory_entry.is_reparse
                or not directory_entry.is_directory
                or entry is None
                or entry.is_reparse
                or not entry.is_regular_file
            ):
                raise MaterializedResumeCheckpointError(
                    "Materialized checkpoint entry is unsafe."
                )
            checkpoint, exact_bytes = read_materialized_resume_checkpoint(
                checkpoint_path
            )
        except (
            OSError,
            ValueError,
            RunPathReferenceError,
            MaterializedResumeCheckpointError,
        ) as exc:
            raise RunRecordIntegrityError(
                "materialized resume checkpoint is invalid",
                reason_code="invalid_resume_checkpoint",
            ) from exc
        if (
            checkpoint_sha256(exact_bytes)
            != request.get("resume_checkpoint_sha256")
            or checkpoint.get("source_job_id") != source_job_id
            or checkpoint.get("source_stage")
            != request.get("resume_checkpoint_stage")
            or checkpoint.get("source_trace_index")
            != request.get("resume_trace_index")
        ):
            raise RunRecordIntegrityError(
                "materialized resume checkpoint identity differs from the run",
                reason_code="invalid_resume_checkpoint",
            )
        return

    source_run_dir = runs_root / source_job_id
    try:
        Path(source_run_dir.absolute()).relative_to(Path(runs_root.absolute()))
        checkpoint_path = resolve_run_reference(
            source_run_dir,
            str(checkpoint_reference),
            mode=record.get("path_reference_mode"),
        )
    except (OSError, ValueError, RunPathReferenceError) as exc:
        raise RunRecordIntegrityError(
            "resume checkpoint path is outside its source run",
            reason_code="invalid_run_path_reference",
        ) from exc
    if not checkpoint_path.is_file():
        raise RunRecordIntegrityError(
            "resume checkpoint path is missing",
            reason_code="invalid_run_path_reference",
        )


def read_canonical_run_record(
    record_path: Path,
    *,
    runs_dir: Path | None = None,
) -> dict[str, Any]:
    """Read and validate one canonical application run record.

    This domain boundary never translates failures into HTTP responses and
    never guesses missing identity from a damaged payload.
    """

    path = Path(record_path)
    try:
        payload = read_json_file(path)
    except FileNotFoundError as exc:
        raise RunRecordIntegrityError("canonical record is missing") from exc
    except UnicodeDecodeError as exc:
        raise RunRecordIntegrityError("canonical record is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise RunRecordIntegrityError("canonical record contains malformed JSON") from exc
    except OSError as exc:
        raise RunRecordIntegrityError("canonical record could not be read") from exc
    record = validate_canonical_run_record(payload)
    validate_canonical_run_record_context(
        record,
        record_path=path,
        runs_dir=runs_dir,
    )
    return record


__all__ = [
    "CanonicalRunRecord",
    "CanonicalRunRequest",
    "RunRecordIntegrityError",
    "read_canonical_run_record",
    "validate_canonical_run_record",
    "validate_canonical_run_record_context",
]
