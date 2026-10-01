from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, SerializeAsAny, field_validator, model_validator

from core.artifacts.models import CheckpointManifestRow


class HarnessExecutorId(StrEnum):
    """Closed identities for the built-in harness executors."""

    STRUCTURED_PATCH_LEGACY = "structured_patch_legacy"
    STRUCTURED_PATCH_REFINED = "structured_patch_refined"
    DIRECT_BASELINE = "direct_baseline"


class RuntimeModelBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    base_url: str | None = None
    max_completion_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0)
    top_p: float | None = Field(default=None, ge=0, le=1)
    timeout_seconds: float = Field(default=600.0, ge=1)
    reasoning_effort: str | None = None
    provider_options: dict[str, JsonValue] = Field(default_factory=dict)
    model_parameters: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("provider", "model")
    @classmethod
    def require_nonempty_identity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Model binding provider and model must be nonempty.")
        return normalized


class RuntimeConfigBase(BaseModel):
    """The real browser/catalog runtime shape, including provider controls."""

    model_config = ConfigDict(extra="forbid")

    provider: str = "gemini"
    model: str = ""
    gemini_base_url: str | None = None
    model_bindings: dict[str, RuntimeModelBinding] = Field(default_factory=dict)
    max_iterations: int = Field(default=1000, ge=1)
    batch_retries: int = Field(default=3, ge=0)
    no_progress_iterations: int = Field(default=2, ge=1)
    num_predict: int | None = Field(default=32768, ge=1)
    think: bool | None = False
    language_repair: bool = True
    semantic_critic: bool = True
    completion_check: bool = True
    infer_implicit_identifiers: bool = True
    temperature: float | None = Field(default=None, ge=0)
    top_p: float | None = Field(default=None, ge=0, le=1)
    timeout_seconds: float = Field(default=600.0, ge=1)
    auto_correction_sequence: bool = False


class StructuredPatchEffectiveConfig(RuntimeConfigBase):
    correction_template_id: str | None = None
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    direct_microop_judge: bool = False
    max_correction_operations: int | None = Field(default=None, ge=1, le=100)


class DirectBaselineEffectiveConfig(RuntimeConfigBase):
    prompt_profile: str = "schema_only_v1"


class HarnessDefinition(BaseModel):
    """Validated catalog definition with typed nested bindings/configuration."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    name: str
    definition_revision: str
    description: str
    runnable: bool
    family: Literal["structured_patch", "direct_baseline"]
    runtime_endpoint: str | None = None
    runtime_note: str | None = None
    runtime_config: SerializeAsAny[RuntimeConfigBase]
    runtime_config_declared: bool = Field(default=False, exclude=True, repr=False)
    model_bindings: dict[str, RuntimeModelBinding] = Field(default_factory=dict)
    model_binding_slots: list[str] = Field(default_factory=lambda: ["default"])
    supported_providers: list[str] = Field(default_factory=list)
    required_capabilities: dict[str, bool] = Field(default_factory=dict)
    prompt_profile: str | None = None
    executor_id: HarnessExecutorId
    script_config: dict[str, JsonValue] | None = None

    @model_validator(mode="before")
    @classmethod
    def copy_and_type_runtime_config(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        copied = deepcopy(value)
        copied["runtime_config_declared"] = "runtime_config" in copied
        family = copied.get("family")
        config_type = (
            StructuredPatchEffectiveConfig
            if family == "structured_patch"
            else DirectBaselineEffectiveConfig
        )
        runtime_config = deepcopy(copied.get("runtime_config") or {})
        if (
            family == "direct_baseline"
            and copied.get("prompt_profile")
            and "prompt_profile" not in runtime_config
        ):
            runtime_config["prompt_profile"] = copied["prompt_profile"]
        copied["runtime_config"] = config_type.model_validate(runtime_config)
        return copied

    @model_validator(mode="after")
    def require_consistent_definition(self) -> HarnessDefinition:
        if not self.definition_revision.strip():
            raise ValueError("Harness definition_revision must not be empty.")
        expected_type = (
            StructuredPatchEffectiveConfig
            if self.family == "structured_patch"
            else DirectBaselineEffectiveConfig
        )
        if not isinstance(self.runtime_config, expected_type):
            raise ValueError(f"{self.family} harness uses the wrong runtime configuration type.")
        structured_executors = {
            HarnessExecutorId.STRUCTURED_PATCH_LEGACY,
            HarnessExecutorId.STRUCTURED_PATCH_REFINED,
        }
        if self.family == "structured_patch" and self.executor_id not in structured_executors:
            raise ValueError("Structured-patch harness uses an incompatible executor.")
        if self.family == "direct_baseline" and self.executor_id != HarnessExecutorId.DIRECT_BASELINE:
            raise ValueError("Direct-baseline harness uses an incompatible executor.")
        if self.executor_id == HarnessExecutorId.STRUCTURED_PATCH_REFINED:
            assert isinstance(self.runtime_config, StructuredPatchEffectiveConfig)
            if not self.runtime_config.auto_correction_sequence:
                raise ValueError("Refined structured-patch correction cannot be disabled.")
            if not (self.runtime_config.correction_template_id or "").strip():
                raise ValueError("Refined structured-patch executor requires a correction template.")
            if self.runtime_config.language_repair:
                raise ValueError("Refined structured-patch language repair must remain disabled.")
        return self

    def to_legacy_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible value for legacy catalog consumers."""

        payload = self.model_dump(mode="json")
        payload["runtime_config"] = self.runtime_config.model_dump(mode="json", exclude_unset=True)
        if not self.runtime_config_declared:
            payload.pop("runtime_config", None)
        if self.runtime_note is None:
            payload.pop("runtime_note", None)
        if self.runtime_endpoint is None:
            payload.pop("runtime_endpoint", None)
        if self.prompt_profile is None:
            payload.pop("prompt_profile", None)
        if self.script_config is None:
            payload.pop("script_config", None)
        return deepcopy(payload)


class EffectiveHarnessRunSpec(BaseModel):
    """Detached identity/configuration boundary for a materialized run."""

    model_config = ConfigDict(extra="forbid")

    harness_id: str
    definition_revision: str
    executor_id: HarnessExecutorId
    family: Literal["structured_patch", "direct_baseline"]
    effective_config: SerializeAsAny[RuntimeConfigBase]
    model_bindings: dict[str, RuntimeModelBinding]

    @model_validator(mode="before")
    @classmethod
    def copy_and_type_effective_config(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        copied = deepcopy(value)
        config_type = (
            StructuredPatchEffectiveConfig
            if copied.get("family") == "structured_patch"
            else DirectBaselineEffectiveConfig
        )
        copied["effective_config"] = config_type.model_validate(copied.get("effective_config") or {})
        return copied

    @model_validator(mode="after")
    def require_family_configuration(self) -> EffectiveHarnessRunSpec:
        expected_type = (
            StructuredPatchEffectiveConfig
            if self.family == "structured_patch"
            else DirectBaselineEffectiveConfig
        )
        if not isinstance(self.effective_config, expected_type):
            raise ValueError(f"{self.family} run uses the wrong effective configuration type.")
        structured_executors = {
            HarnessExecutorId.STRUCTURED_PATCH_LEGACY,
            HarnessExecutorId.STRUCTURED_PATCH_REFINED,
        }
        if self.family == "structured_patch" and self.executor_id not in structured_executors:
            raise ValueError("Structured-patch run uses an incompatible executor.")
        if self.family == "direct_baseline" and self.executor_id != HarnessExecutorId.DIRECT_BASELINE:
            raise ValueError("Direct-baseline run uses an incompatible executor.")
        if self.executor_id == HarnessExecutorId.STRUCTURED_PATCH_REFINED:
            assert isinstance(self.effective_config, StructuredPatchEffectiveConfig)
            if not self.effective_config.auto_correction_sequence:
                raise ValueError("Refined structured-patch correction cannot be disabled.")
            if not (self.effective_config.correction_template_id or "").strip():
                raise ValueError("Refined structured-patch executor requires a correction template.")
            if self.effective_config.language_repair:
                raise ValueError("Refined structured-patch language repair must remain disabled.")
        return self

    def detached_copy(self) -> EffectiveHarnessRunSpec:
        return self.model_copy(deep=True)


class HarnessDomainEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1)
    payload: dict[str, JsonValue]

    @classmethod
    def from_parts(cls, event_type: str, payload: dict[str, Any]) -> HarnessDomainEvent:
        return cls.model_validate({"type": event_type, "payload": deepcopy(payload)})

    def detached_parts(self) -> tuple[str, dict[str, Any]]:
        dumped = self.model_dump(mode="json")
        return str(dumped["type"]), deepcopy(dumped["payload"])


class CheckpointArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    stage: str
    timestamp_utc: str
    payload: dict[str, JsonValue]


class CheckpointReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    stage: str
    path: str
    timestamp_utc: str


class CorrectionSequenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    changed_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    deferred_count: int = Field(default=0, ge=0)
    checkpoint_stage: str = ""


HarnessCheckpointRow = CheckpointManifestRow


__all__ = [
    "CheckpointArtifact",
    "CheckpointReference",
    "CorrectionSequenceSummary",
    "DirectBaselineEffectiveConfig",
    "EffectiveHarnessRunSpec",
    "HarnessCheckpointRow",
    "HarnessDefinition",
    "HarnessDomainEvent",
    "HarnessExecutorId",
    "RuntimeModelBinding",
    "StructuredPatchEffectiveConfig",
]
