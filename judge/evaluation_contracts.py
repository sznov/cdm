from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.config_safety import (
    is_sensitive_config_key,
    redact_sensitive_text,
    validate_secret_free_mapping,
)
from core.model_bindings import validate_model_bindings_security


EVALUATION_SCHEMA_VERSION = 1
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ABSOLUTE_LOCAL_PATH_PATTERN = re.compile(
    r"(?:^|[\s\"'(:])(?:[A-Za-z]:[\\/]|\\\\|/(?!/))"
)


def _nonempty_identifier(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if len(normalized) > 200:
        raise ValueError(f"{field_name} must be at most 200 characters")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError(f"{field_name} must not contain control characters")
    return normalized


def validate_portable_metadata(value: object, *, path: str) -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            validate_portable_metadata(
                nested,
                path=f"{path}.{raw_key}",
            )
        return
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for index, nested in enumerate(value):
            validate_portable_metadata(nested, path=f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return
    if (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or ABSOLUTE_LOCAL_PATH_PATTERN.search(value)
    ):
        raise ValueError(
            f"machine-local absolute paths are not allowed at {path}"
        )


class StrictEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactDescriptor(StrictEvaluationModel):
    path: str = Field(min_length=1)
    media_type: str | None = None
    schema_id: str | None = None
    sha256: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return normalized

    @field_validator("path")
    @classmethod
    def validate_path_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("artifact paths must not contain NUL bytes")
        return value


class MaterializedArtifact(StrictEvaluationModel):
    path: str = Field(min_length=1)
    media_type: str | None = None
    schema_id: str | None = None
    sha256: str
    size_bytes: int = Field(ge=0)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        return normalized

    @field_validator("path")
    @classmethod
    def validate_path_text(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("artifact paths must not contain NUL bytes")
        return value


class DatasetCase(StrictEvaluationModel):
    case_id: str
    inputs: dict[str, ArtifactDescriptor] = Field(min_length=1)
    references: dict[str, ArtifactDescriptor] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("case_id")
    @classmethod
    def validate_case_id(cls, value: str) -> str:
        return _nonempty_identifier(value, field_name="case_id")

    @field_validator("inputs", "references")
    @classmethod
    def validate_artifact_roles(
        cls,
        value: dict[str, ArtifactDescriptor],
    ) -> dict[str, ArtifactDescriptor]:
        for role in value:
            _nonempty_identifier(role, field_name="artifact role")
        return value

    @model_validator(mode="after")
    def validate_metadata(self) -> DatasetCase:
        validate_secret_free_mapping(self.metadata, path="metadata")
        validate_portable_metadata(self.metadata, path="metadata")
        return self


class EvaluationDataset(StrictEvaluationModel):
    artifact_kind: Literal["evaluation_dataset"] = "evaluation_dataset"
    schema_version: Literal[1] = EVALUATION_SCHEMA_VERSION
    dataset_id: str
    cases: list[DatasetCase] = Field(min_length=1)

    @field_validator("dataset_id")
    @classmethod
    def validate_dataset_id(cls, value: str) -> str:
        return _nonempty_identifier(value, field_name="dataset_id")

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> EvaluationDataset:
        identifiers = [case.case_id for case in self.cases]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("dataset case_id values must be unique")
        return self


class CommandAdapter(StrictEvaluationModel):
    implementation_id: str
    revision: str
    argv: list[str] = Field(min_length=1)
    timeout_seconds: float = Field(default=900.0, gt=0, le=86_400)
    environment_allowlist: list[str] = Field(default_factory=list)
    max_attempts: int = Field(default=1, ge=1, le=10)

    @field_validator("implementation_id", "revision")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _nonempty_identifier(value, field_name=info.field_name)

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, value: list[str]) -> list[str]:
        if any(not isinstance(argument, str) or "\x00" in argument for argument in value):
            raise ValueError("adapter argv entries must be strings without NUL bytes")
        if not value[0].strip():
            raise ValueError("adapter executable must not be empty")
        for argument in value:
            if redact_sensitive_text(
                argument,
                redact_named_values=True,
                redact_url_fragments=True,
            ) != argument:
                raise ValueError(
                    "adapter credentials must use the environment allowlist, "
                    "not argv"
                )
        for argument in value[1:]:
            if not argument.startswith("-"):
                continue
            name = argument.lstrip("-").split("=", 1)[0]
            if is_sensitive_config_key(name):
                raise ValueError(
                    "adapter credentials must use the environment allowlist, "
                    "not argv"
                )
        return value

    @field_validator("environment_allowlist")
    @classmethod
    def validate_environment_allowlist(cls, value: list[str]) -> list[str]:
        if len(value) != len({name.casefold() for name in value}):
            raise ValueError("environment_allowlist values must be unique")
        for name in value:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise ValueError(f"invalid environment variable name: {name!r}")
        return value


class CatalogGenerationSource(StrictEvaluationModel):
    kind: Literal["catalog_harness"]
    source_id: str
    harness_id: str
    definition_revision: str
    provider: Literal["gemini", "codex", "nvidia_nim"]
    model: str
    repetitions: int = Field(default=1, ge=1, le=100)
    input_role: str = "specification"
    reference_role: str = "reference_model"
    runtime_config: dict[str, Any] = Field(default_factory=dict)
    model_bindings: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=900.0, gt=0, le=86_400)
    max_attempts: int = Field(default=3, ge=1, le=10)
    target_valid_generations: int | None = Field(default=None, ge=1, le=100)
    fill_max_attempts: int | None = Field(default=None, ge=1, le=1000)
    codex_reasoning_effort: str | None = None

    @field_validator("source_id", "harness_id", "definition_revision", "model")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _nonempty_identifier(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_security_and_fill_policy(self) -> CatalogGenerationSource:
        validate_model_bindings_security(self.model_bindings)
        validate_secret_free_mapping(self.runtime_config, path="runtime_config")
        if (
            self.target_valid_generations is not None
            and self.fill_max_attempts is not None
            and self.fill_max_attempts < self.target_valid_generations
        ):
            raise ValueError("fill_max_attempts must be at least target_valid_generations")
        return self


class CommandGenerationSource(StrictEvaluationModel):
    kind: Literal["command"]
    source_id: str
    repetitions: int = Field(default=1, ge=1, le=100)
    adapter: CommandAdapter

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        return _nonempty_identifier(value, field_name="source_id")


class CandidateManifestGenerationSource(StrictEvaluationModel):
    kind: Literal["candidate_manifest"]
    source_id: str
    manifest: ArtifactDescriptor

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        return _nonempty_identifier(value, field_name="source_id")


class ArchivedModelGenerationSource(StrictEvaluationModel):
    kind: Literal["archived_models"]
    source_id: str
    archive_root: str
    canonical_manifest: str = "results/canonical_run_manifest.json"

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        return _nonempty_identifier(value, field_name="source_id")


GenerationSource = Annotated[
    CatalogGenerationSource
    | CommandGenerationSource
    | CandidateManifestGenerationSource
    | ArchivedModelGenerationSource,
    Field(discriminator="kind"),
]


class SystemView(StrictEvaluationModel):
    system_id: str
    source_id: str
    checkpoint_or_view: str
    artifact_roles: dict[str, str] = Field(default_factory=lambda: {"model": "model"})
    label: str | None = None

    @field_validator("system_id", "source_id", "checkpoint_or_view")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _nonempty_identifier(value, field_name=info.field_name)

    @field_validator("artifact_roles")
    @classmethod
    def validate_artifact_roles(
        cls,
        value: dict[str, str],
    ) -> dict[str, str]:
        for candidate_role, source_role in value.items():
            _nonempty_identifier(candidate_role, field_name="candidate artifact role")
            _nonempty_identifier(source_role, field_name="source artifact role")
        if len(value.values()) != len(set(value.values())):
            raise ValueError("system-view source artifact roles must be unique")
        return value


class DirectionalJudgeSource(StrictEvaluationModel):
    kind: Literal["directional_structured_model_v1"]
    judge_id: str
    provider: Literal["gemini", "codex", "nvidia_nim"]
    model: str
    prompt_profile: str
    repetitions: int = Field(default=5, ge=1, le=100)
    majority_threshold: int | None = Field(default=None, ge=1, le=100)
    timeout_seconds: float = Field(default=1800.0, gt=0, le=86_400)
    max_attempts: int = Field(default=1, ge=1, le=10)
    reasoning_effort: str | None = None
    input_role: str = "specification"
    reference_role: str = "reference_model"
    candidate_role: str = "model"

    @field_validator("judge_id", "model", "prompt_profile")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _nonempty_identifier(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_threshold(self) -> DirectionalJudgeSource:
        threshold = self.majority_threshold or (self.repetitions // 2 + 1)
        if threshold > self.repetitions:
            raise ValueError("majority_threshold cannot exceed repetitions")
        return self


class CommandJudgeSource(StrictEvaluationModel):
    kind: Literal["command"]
    judge_id: str
    repetitions: int = Field(default=1, ge=1, le=100)
    adapter: CommandAdapter

    @field_validator("judge_id")
    @classmethod
    def validate_judge_id(cls, value: str) -> str:
        return _nonempty_identifier(value, field_name="judge_id")


class StoredResultJudgeSource(StrictEvaluationModel):
    kind: Literal["stored_result_manifest"]
    judge_id: str
    manifest: ArtifactDescriptor
    reducer_revision: str
    repetitions: int = Field(default=1, ge=1, le=100)
    majority_threshold: int | None = Field(default=None, ge=1, le=100)

    @field_validator("judge_id", "reducer_revision")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _nonempty_identifier(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_threshold(self) -> StoredResultJudgeSource:
        if (
            self.majority_threshold is not None
            and self.majority_threshold > self.repetitions
        ):
            raise ValueError("majority_threshold cannot exceed repetitions")
        return self


JudgeSource = Annotated[
    DirectionalJudgeSource | CommandJudgeSource | StoredResultJudgeSource,
    Field(discriminator="kind"),
]


class MetricDefinition(StrictEvaluationModel):
    metric_id: str
    label: str
    direction: Literal["higher", "lower"]
    minimum: float | None = None
    maximum: float | None = None
    repeat_reduction: Literal["mean", "median", "directional_majority_v1"] = "mean"

    @field_validator("metric_id", "label")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _nonempty_identifier(value, field_name=info.field_name)

    @field_validator("minimum", "maximum")
    @classmethod
    def validate_finite_bound(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("metric bounds must be finite")
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> MetricDefinition:
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("metric minimum cannot exceed maximum")
        return self


class SystemComparison(StrictEvaluationModel):
    comparison_id: str
    left_system_id: str
    right_system_id: str
    metric_ids: list[str] = Field(min_length=1)

    @field_validator("comparison_id", "left_system_id", "right_system_id")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _nonempty_identifier(value, field_name=info.field_name)

    @field_validator("metric_ids")
    @classmethod
    def validate_metric_ids(cls, value: list[str]) -> list[str]:
        for metric_id in value:
            _nonempty_identifier(metric_id, field_name="metric id")
        if len(value) != len(set(value)):
            raise ValueError("comparison metric_ids must be unique")
        return value


class EvaluationStatistics(StrictEvaluationModel):
    bootstrap_samples: int = Field(default=0, ge=0, le=1_000_000)
    bootstrap_seed: int = 20260523
    confidence_level: float = Field(default=0.95, gt=0, lt=1)


class EvaluationExecution(StrictEvaluationModel):
    generation_concurrency: int = Field(default=1, ge=1, le=128)
    judge_concurrency: int = Field(default=1, ge=1, le=128)


class EvaluationSuite(StrictEvaluationModel):
    artifact_kind: Literal["evaluation_suite"] = "evaluation_suite"
    schema_version: Literal[1] = EVALUATION_SCHEMA_VERSION
    suite_id: str
    dataset: str
    generation_sources: list[GenerationSource] = Field(min_length=1)
    system_views: list[SystemView] = Field(min_length=1)
    judges: list[JudgeSource] = Field(min_length=1)
    metrics: list[MetricDefinition] = Field(min_length=1)
    comparisons: list[SystemComparison] = Field(default_factory=list)
    statistics: EvaluationStatistics = Field(default_factory=EvaluationStatistics)
    execution: EvaluationExecution = Field(default_factory=EvaluationExecution)
    claims: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("suite_id")
    @classmethod
    def validate_suite_id(cls, value: str) -> str:
        return _nonempty_identifier(value, field_name="suite_id")

    @model_validator(mode="after")
    def validate_references(self) -> EvaluationSuite:
        source_ids = [source.source_id for source in self.generation_sources]
        system_ids = [view.system_id for view in self.system_views]
        judge_ids = [judge.judge_id for judge in self.judges]
        metric_ids = [metric.metric_id for metric in self.metrics]
        comparison_ids = [
            comparison.comparison_id for comparison in self.comparisons
        ]
        for label, identifiers in (
            ("generation source", source_ids),
            ("system view", system_ids),
            ("judge", judge_ids),
            ("metric", metric_ids),
            ("comparison", comparison_ids),
        ):
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"{label} identifiers must be unique")
        for view in self.system_views:
            if view.source_id not in source_ids:
                raise ValueError(
                    f"system view {view.system_id!r} references unknown source {view.source_id!r}"
                )
        for comparison in self.comparisons:
            if comparison.left_system_id not in system_ids:
                raise ValueError(
                    f"comparison {comparison.comparison_id!r} references unknown left system"
                )
            if comparison.right_system_id not in system_ids:
                raise ValueError(
                    f"comparison {comparison.comparison_id!r} references unknown right system"
                )
            unknown_metrics = sorted(set(comparison.metric_ids) - set(metric_ids))
            if unknown_metrics:
                raise ValueError(
                    f"comparison {comparison.comparison_id!r} references unknown metrics: "
                    + ", ".join(unknown_metrics)
                )
        validate_secret_free_mapping(self.metadata, path="metadata")
        validate_portable_metadata(self.metadata, path="metadata")
        return self


class CandidateRecord(StrictEvaluationModel):
    system_id: str
    case_id: str
    sample_id: str
    checkpoint_or_view: str
    artifacts: dict[str, MaterializedArtifact] = Field(min_length=1)
    generator_provenance: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] | None = None

    @field_validator("system_id", "case_id", "sample_id", "checkpoint_or_view")
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _nonempty_identifier(value, field_name=info.field_name)

    @field_validator("artifacts")
    @classmethod
    def validate_artifact_roles(
        cls,
        value: dict[str, MaterializedArtifact],
    ) -> dict[str, MaterializedArtifact]:
        for role in value:
            _nonempty_identifier(role, field_name="artifact role")
        return value

    @model_validator(mode="after")
    def validate_secret_free_metadata(self) -> CandidateRecord:
        validate_secret_free_mapping(
            self.generator_provenance,
            path="generator_provenance",
        )
        validate_portable_metadata(
            self.generator_provenance,
            path="generator_provenance",
        )
        if self.usage is not None:
            validate_secret_free_mapping(self.usage, path="usage")
            validate_portable_metadata(self.usage, path="usage")
        return self


class EvaluationCandidateManifest(StrictEvaluationModel):
    artifact_kind: Literal["evaluation_candidate_manifest"] = "evaluation_candidate_manifest"
    schema_version: Literal[1] = EVALUATION_SCHEMA_VERSION
    candidates: list[CandidateRecord]

    @model_validator(mode="after")
    def require_unique_candidates(self) -> EvaluationCandidateManifest:
        keys = [
            (row.system_id, row.case_id, row.sample_id, row.checkpoint_or_view)
            for row in self.candidates
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("candidate identities must be unique")
        return self


class GeneratorAdapterRequest(StrictEvaluationModel):
    artifact_kind: Literal["evaluation_generator_request"] = "evaluation_generator_request"
    schema_version: Literal[1] = EVALUATION_SCHEMA_VERSION
    request_id: str
    source_id: str
    system_views: list[SystemView]
    case_id: str
    sample_id: str
    inputs: dict[str, MaterializedArtifact]
    references: dict[str, MaterializedArtifact]
    output_dir: str


class GeneratorAdapterResponse(StrictEvaluationModel):
    artifact_kind: Literal["evaluation_generator_response"] = "evaluation_generator_response"
    schema_version: Literal[1] = EVALUATION_SCHEMA_VERSION
    status: Literal["completed", "failed"]
    artifacts_by_view: dict[str, dict[str, ArtifactDescriptor]] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_completed_payload(self) -> GeneratorAdapterResponse:
        if self.status == "completed" and not self.artifacts_by_view:
            raise ValueError("completed generator response requires artifacts_by_view")
        validate_secret_free_mapping(self.provenance, path="provenance")
        validate_portable_metadata(self.provenance, path="provenance")
        if self.usage is not None:
            validate_secret_free_mapping(self.usage, path="usage")
            validate_portable_metadata(self.usage, path="usage")
        return self


class JudgeAdapterRequest(StrictEvaluationModel):
    artifact_kind: Literal["evaluation_judge_request"] = "evaluation_judge_request"
    schema_version: Literal[1] = EVALUATION_SCHEMA_VERSION
    request_id: str
    judge_id: str
    repeat_index: int = Field(ge=1)
    candidate: CandidateRecord
    inputs: dict[str, MaterializedArtifact]
    references: dict[str, MaterializedArtifact]
    declared_metrics: list[MetricDefinition]


class JudgeAdapterResponse(StrictEvaluationModel):
    artifact_kind: Literal["evaluation_judge_response"] = "evaluation_judge_response"
    schema_version: Literal[1] = EVALUATION_SCHEMA_VERSION
    status: Literal["completed", "failed"]
    metrics: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] | None = None
    error: str | None = None

    @field_validator("metrics")
    @classmethod
    def validate_finite_metrics(cls, value: dict[str, float]) -> dict[str, float]:
        for metric_id, metric_value in value.items():
            _nonempty_identifier(metric_id, field_name="metric id")
            if not math.isfinite(metric_value):
                raise ValueError(f"metric {metric_id!r} must be finite")
        return value

    @model_validator(mode="after")
    def validate_completed_payload(self) -> JudgeAdapterResponse:
        if self.status == "completed" and not self.metrics:
            raise ValueError("completed judge response requires metrics")
        validate_secret_free_mapping(self.details, path="details")
        validate_portable_metadata(self.details, path="details")
        if self.usage is not None:
            validate_secret_free_mapping(self.usage, path="usage")
            validate_portable_metadata(self.usage, path="usage")
        for field_name, value in (("notes", self.notes), ("error", self.error)):
            if value:
                validate_portable_metadata(value, path=field_name)
        return self


class JudgeResultRecord(StrictEvaluationModel):
    result_id: str
    judge_id: str
    system_id: str
    case_id: str
    sample_id: str
    checkpoint_or_view: str
    repeat_index: int = Field(ge=1)
    status: Literal["completed", "failed", "timeout"]
    metrics: dict[str, float] = Field(default_factory=dict)
    notes: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] | None = None
    error: str | None = None

    @field_validator(
        "result_id",
        "judge_id",
        "system_id",
        "case_id",
        "sample_id",
        "checkpoint_or_view",
    )
    @classmethod
    def validate_identity(cls, value: str, info: Any) -> str:
        return _nonempty_identifier(value, field_name=info.field_name)

    @field_validator("metrics")
    @classmethod
    def validate_finite_metrics(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not math.isfinite(metric_value) for metric_value in value.values()):
            raise ValueError("judge result metrics must be finite")
        return value

    @model_validator(mode="after")
    def validate_secret_free_metadata(self) -> JudgeResultRecord:
        validate_secret_free_mapping(self.details, path="details")
        validate_portable_metadata(self.details, path="details")
        if self.usage is not None:
            validate_secret_free_mapping(self.usage, path="usage")
            validate_portable_metadata(self.usage, path="usage")
        for field_name, value in (("notes", self.notes), ("error", self.error)):
            if value:
                validate_portable_metadata(value, path=field_name)
        return self


class StoredJudgeResultManifest(StrictEvaluationModel):
    artifact_kind: Literal["evaluation_judge_result_manifest"] = (
        "evaluation_judge_result_manifest"
    )
    schema_version: Literal[1] = EVALUATION_SCHEMA_VERSION
    results: list[JudgeResultRecord]

    @model_validator(mode="after")
    def require_unique_results(self) -> StoredJudgeResultManifest:
        result_ids = [result.result_id for result in self.results]
        identities = [
            (
                result.judge_id,
                result.system_id,
                result.case_id,
                result.sample_id,
                result.checkpoint_or_view,
                result.repeat_index,
            )
            for result in self.results
        ]
        if len(result_ids) != len(set(result_ids)):
            raise ValueError("stored judge result_id values must be unique")
        if len(identities) != len(set(identities)):
            raise ValueError("stored judge result identities must be unique")
        return self


class EvaluationClaim(StrictEvaluationModel):
    claim_id: str
    report_reference: str
    system_id: str | None = None
    comparison_id: str | None = None
    judge_id: str | None = None
    metric_id: str
    expected_value: float | None = None
    expected_count: int | None = Field(default=None, ge=0)
    tolerance: float = Field(default=0.0, ge=0)
    display_decimals: int | None = Field(default=None, ge=0, le=12)

    @field_validator("claim_id", "report_reference", "metric_id", "judge_id")
    @classmethod
    def validate_identity(
        cls,
        value: str | None,
        info: Any,
    ) -> str | None:
        if value is None:
            return None
        return _nonempty_identifier(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_selector_and_expected_value(self) -> EvaluationClaim:
        if (self.system_id is None) == (self.comparison_id is None):
            raise ValueError("claim must select exactly one system_id or comparison_id")
        if (self.expected_value is None) == (self.expected_count is None):
            raise ValueError(
                "claim must define exactly one expected_value or expected_count"
            )
        if self.expected_value is not None and not math.isfinite(self.expected_value):
            raise ValueError("claim expected_value must be finite")
        return self


class EvaluationSystemClaimGroup(StrictEvaluationModel):
    claim_id_prefix: str
    report_reference: str
    system_id: str
    judge_id: str | None = None
    expected_values: dict[str, float] = Field(min_length=1)
    tolerance: float = Field(default=0.0, ge=0)
    display_decimals: int | None = Field(default=None, ge=0, le=12)

    @field_validator(
        "claim_id_prefix",
        "report_reference",
        "system_id",
        "judge_id",
    )
    @classmethod
    def validate_identity(
        cls,
        value: str | None,
        info: Any,
    ) -> str | None:
        if value is None:
            return None
        return _nonempty_identifier(value, field_name=info.field_name)

    @field_validator("expected_values")
    @classmethod
    def validate_expected_values(
        cls,
        value: dict[str, float],
    ) -> dict[str, float]:
        for metric_id, expected_value in value.items():
            _nonempty_identifier(metric_id, field_name="metric id")
            if not math.isfinite(expected_value):
                raise ValueError(
                    f"claim expected value for {metric_id!r} must be finite"
                )
        return value

    def expand(self) -> list[EvaluationClaim]:
        return [
            EvaluationClaim(
                claim_id=(
                    f"{self.claim_id_prefix}-"
                    f"{metric_id.replace('_', '-')}"
                ),
                report_reference=f"{self.report_reference} / {metric_id}",
                system_id=self.system_id,
                judge_id=self.judge_id,
                metric_id=metric_id,
                expected_value=expected_value,
                tolerance=self.tolerance,
                display_decimals=self.display_decimals,
            )
            for metric_id, expected_value in self.expected_values.items()
        ]


class EvaluationClaimsManifest(StrictEvaluationModel):
    artifact_kind: Literal["evaluation_claims"] = "evaluation_claims"
    schema_version: Literal[1] = EVALUATION_SCHEMA_VERSION
    claims_id: str
    claims: list[EvaluationClaim] = Field(default_factory=list)
    system_claim_groups: list[EvaluationSystemClaimGroup] = Field(
        default_factory=list
    )

    @field_validator("claims_id")
    @classmethod
    def validate_claims_id(cls, value: str) -> str:
        return _nonempty_identifier(value, field_name="claims_id")

    @model_validator(mode="after")
    def require_unique_claim_ids(self) -> EvaluationClaimsManifest:
        expanded = self.expanded_claims()
        if not expanded:
            raise ValueError("claims manifest must contain at least one claim")
        identifiers = [claim.claim_id for claim in expanded]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("claim_id values must be unique")
        return self

    def expanded_claims(self) -> list[EvaluationClaim]:
        expanded = list(self.claims)
        for group in self.system_claim_groups:
            expanded.extend(group.expand())
        return expanded


__all__ = [
    "ArchivedModelGenerationSource",
    "ArtifactDescriptor",
    "CandidateManifestGenerationSource",
    "CandidateRecord",
    "CatalogGenerationSource",
    "CommandAdapter",
    "CommandGenerationSource",
    "CommandJudgeSource",
    "DatasetCase",
    "DirectionalJudgeSource",
    "EVALUATION_SCHEMA_VERSION",
    "EvaluationCandidateManifest",
    "EvaluationClaim",
    "EvaluationClaimsManifest",
    "EvaluationDataset",
    "EvaluationExecution",
    "EvaluationStatistics",
    "EvaluationSuite",
    "EvaluationSystemClaimGroup",
    "GeneratorAdapterRequest",
    "GeneratorAdapterResponse",
    "JudgeAdapterRequest",
    "JudgeAdapterResponse",
    "JudgeResultRecord",
    "MaterializedArtifact",
    "MetricDefinition",
    "StoredJudgeResultManifest",
    "StoredResultJudgeSource",
    "SystemComparison",
    "SystemView",
    "validate_portable_metadata",
]
