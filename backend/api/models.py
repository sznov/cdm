from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.api.settings import DEFAULT_CORRECTION_TEMPLATE_ID, DEFAULT_RUNTIME_HARNESS_ID
from core.config_safety import validate_secret_free_mapping
from core.model_bindings import (
    validate_model_bindings_security,
)
from harnesses.contracts import RuntimeModelBinding


class HarnessRuntimeConfigOverrides(BaseModel):
    """Workflow-only overrides accepted by the application API boundary.

    Provider, model, endpoint, and model-call controls belong exclusively to
    ``model_bindings``.  Keeping this model closed prevents a second,
    conflicting representation from reaching preparation.
    """

    model_config = ConfigDict(extra="forbid")

    max_iterations: int | None = Field(default=None, ge=1, le=1000)
    batch_retries: int | None = Field(default=None, ge=0, le=10)
    no_progress_iterations: int | None = Field(default=None, ge=1, le=100)
    think: bool | None = None
    language_repair: bool | None = None
    semantic_critic: bool | None = None
    completion_check: bool | None = None
    infer_implicit_identifiers: bool | None = None
    auto_correction_sequence: bool | None = None
    correction_template_id: str | None = Field(default=None, min_length=1)
    max_attempts: int | None = Field(default=None, ge=1, le=10)
    direct_microop_judge: bool | None = None
    max_correction_operations: int | None = Field(default=None, ge=1, le=100)
    prompt_profile: str | None = Field(default=None, min_length=1)

    def detached_override(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


def _validate_durable_request_configuration(request: Any) -> None:
    bindings = getattr(request, "model_bindings", None)
    validate_model_bindings_security(
        {
            slot: binding.model_dump(mode="json", exclude_unset=True)
            for slot, binding in bindings.items()
        }
        if isinstance(bindings, dict)
        else None
    )
    runtime_config = getattr(request, "harness_runtime_config", None)
    if not isinstance(runtime_config, HarnessRuntimeConfigOverrides):
        return
    validate_secret_free_mapping(
        runtime_config.detached_override(),
        path="harness_runtime_config",
    )


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_harness_id: str = Field(default=DEFAULT_RUNTIME_HARNESS_ID, pattern=r"^[A-Za-z0-9_-]+$")
    harness_definition_revision: str | None = Field(default=None, min_length=1)
    harness_runtime_config: HarnessRuntimeConfigOverrides | None = None
    model_bindings: dict[str, RuntimeModelBinding] | None = None
    specification: str | None = Field(default=None, min_length=1)
    retry_of_job_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]+$")
    resume_from_job_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]+$")
    resume_trace_index: int | None = Field(default=None, ge=0)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]+$")

    @model_validator(mode="after")
    def require_credential_free_configuration(self) -> RunRequest:
        if self.resume_from_job_id and self.retry_of_job_id:
            raise ValueError("retry_of_job_id and resume_from_job_id are mutually exclusive.")
        if "model_bindings" in self.model_fields_set and (
            not self.model_bindings or "default" not in self.model_bindings
        ):
            raise ValueError("model_bindings.default is required when model_bindings is supplied.")
        _validate_durable_request_configuration(self)
        return self


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=160)
    runtime_harness_id: str = Field(default=DEFAULT_RUNTIME_HARNESS_ID, pattern=r"^[A-Za-z0-9_-]+$")
    harness_definition_revision: str | None = Field(default=None, min_length=1)
    harness_runtime_config: HarnessRuntimeConfigOverrides | None = None
    model_bindings: dict[str, RuntimeModelBinding] | None = None
    specification: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_credential_free_configuration(self) -> SessionCreateRequest:
        if "model_bindings" in self.model_fields_set and (
            not self.model_bindings or "default" not in self.model_bindings
        ):
            raise ValueError("model_bindings.default is required when model_bindings is supplied.")
        _validate_durable_request_configuration(self)
        return self


class SessionPatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    chat_message: dict[str, Any] | None = None
    decision_comment: dict[str, Any] | None = None


class DecisionPatchChoiceRequest(BaseModel):
    patch_id: str = Field(min_length=1)
    option_id: str | None = None
    label: str | None = None
    custom_text: str | None = None


class DecisionPatchApplyRequest(BaseModel):
    patch_ids: list[str] = Field(default_factory=list)
    decisions: list[DecisionPatchChoiceRequest] = Field(default_factory=list)


class CorrectionPatchRequest(BaseModel):
    message: str = Field(min_length=1)
    max_operations: int | None = Field(default=None, ge=1, le=100)
    allowed_ops: list[str] | None = None


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1)


class CorrectionSequenceRequest(BaseModel):
    template_id: str = Field(default=DEFAULT_CORRECTION_TEMPLATE_ID, pattern=r"^[A-Za-z0-9_.-]+$")
    max_operations: int | None = Field(default=None, ge=1, le=100)

__all__ = [
    "CorrectionPatchRequest",
    "CorrectionSequenceRequest",
    "DecisionPatchApplyRequest",
    "DecisionPatchChoiceRequest",
    "QuestionRequest",
    "HarnessRuntimeConfigOverrides",
    "RunRequest",
    "SessionCreateRequest",
    "SessionPatchRequest",
]
