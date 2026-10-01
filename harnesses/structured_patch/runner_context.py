from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.model_call_logger import ModelCallLogger
from core.model_client import TextModelClient
from harnesses.structured_patch.run_events import StructuredPatchRunEvents
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.runner_prompt_profile import AsyncOpPatchPromptProfile


@dataclass(frozen=True, slots=True)
class ModelCallPolicy:
    max_attempts: int
    transport_retries: int | None


@dataclass(frozen=True, slots=True)
class StructuredPatchRunConfig:
    """Deeply immutable scalar/prompt configuration shared by all phases."""

    model_calls: ModelCallPolicy
    infer_implicit_identifiers: bool
    structured_language_repair: bool
    direct_microop_judge: bool
    prompt_profile: AsyncOpPatchPromptProfile
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY


@dataclass(frozen=True, slots=True)
class HarnessRunInputs:
    specification: str
    run_job_id: str
    model_call_log_dir: Path | None
    config: StructuredPatchRunConfig


@dataclass(slots=True)
class HarnessRunContext:
    """Explicit mutable runtime adapters paired with immutable run inputs."""

    inputs: HarnessRunInputs
    client: TextModelClient
    logger: ModelCallLogger
    events: StructuredPatchRunEvents

    @property
    def specification(self) -> str:
        return self.inputs.specification

    @property
    def config(self) -> StructuredPatchRunConfig:
        return self.inputs.config


@dataclass(slots=True)
class RunJournal:
    input_prompts: list[dict[str, Any]] = field(default_factory=list)
    operation_history: list[dict[str, Any]] = field(default_factory=list)
    usage_steps: list[dict[str, Any] | None] = field(default_factory=list)


__all__ = [
    "HarnessRunContext",
    "HarnessRunInputs",
    "ModelCallPolicy",
    "RunJournal",
    "StructuredPatchRunConfig",
]
