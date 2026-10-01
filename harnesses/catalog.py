from __future__ import annotations

from copy import deepcopy
from typing import Any

from core.model_bindings import default_model_binding
from core.providers.factory import DEFAULT_GEMINI_BASE_URL, DEFAULT_GEMINI_MODEL
from harnesses.contracts import (
    DirectBaselineEffectiveConfig,
    EffectiveHarnessRunSpec,
    HarnessDefinition,
    HarnessExecutorId,
    StructuredPatchEffectiveConfig,
)


class HarnessDefinitionRevisionMismatchError(ValueError):
    def __init__(self, *, harness_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Harness definition revision mismatch for {harness_id}: expected "
            f"{expected!r}, catalog provides {actual!r}."
        )
        self.harness_id = harness_id
        self.expected = expected
        self.actual = actual


GEMINI_DEFAULT_MODEL_BINDINGS = {
    "default": default_model_binding("gemini"),
}

DEFAULT_RUNTIME_CONFIG: dict[str, Any] = {
    "provider": "gemini",
    "model": DEFAULT_GEMINI_MODEL,
    "gemini_base_url": DEFAULT_GEMINI_BASE_URL,
    "model_bindings": deepcopy(GEMINI_DEFAULT_MODEL_BINDINGS),
    "max_iterations": 1000,
    "batch_retries": 10,
    "no_progress_iterations": 2,
    "num_predict": 32768,
    "think": False,
    "language_repair": True,
    "semantic_critic": True,
    "completion_check": True,
    "infer_implicit_identifiers": True,
    "temperature": None,
    "top_p": None,
    "timeout_seconds": 600.0,
    "auto_correction_sequence": True,
    "correction_template_id": "single-conservative-correction-pass",
}

DIRECT_BASELINE_RUNTIME_CONFIG: dict[str, Any] = {
    "provider": "gemini",
    "model": DEFAULT_GEMINI_MODEL,
    "gemini_base_url": DEFAULT_GEMINI_BASE_URL,
    "model_bindings": deepcopy(GEMINI_DEFAULT_MODEL_BINDINGS),
    "max_iterations": 1,
    "batch_retries": 3,
    "no_progress_iterations": 1,
    "num_predict": 32768,
    "think": False,
    "language_repair": False,
    "semantic_critic": False,
    "completion_check": False,
    "infer_implicit_identifiers": False,
    "temperature": None,
    "top_p": None,
    "timeout_seconds": 600.0,
    "auto_correction_sequence": False,
    "prompt_profile": "schema_only_v1",
}

GEMMA4_TUNED_FINAL: dict[str, Any] = {
    "id": "gemma4-tuned-final",
    "name": "Gemma 4 Tuned Legacy",
    "definition_revision": "gemma4-tuned-final-20260524",
    "description": (
        "Legacy Structured Patch workflow with language repair and a conservative "
        "final correction pass."
    ),
    "runnable": True,
    "runtime_endpoint": "/api/runs",
    "runtime_note": (
        "Uses the legacy generation, revision, and correction sequence. "
        "The selected provider model remains configurable."
    ),
    "runtime_config": deepcopy(DEFAULT_RUNTIME_CONFIG),
    "model_bindings": deepcopy(GEMINI_DEFAULT_MODEL_BINDINGS),
    "model_binding_slots": ["default"],
    "supported_providers": ["gemini", "nvidia_nim"],
    "required_capabilities": {"streaming": True, "json_response": True},
    "family": "structured_patch",
    "executor_id": HarnessExecutorId.STRUCTURED_PATCH_LEGACY,
    "script_config": {
        "infer_implicit_identifiers": True,
        "language_repair": True,
        "auto_correction_sequence": True,
        "correction_template_id": "single-conservative-correction-pass",
    },
}

REFINED_RUNTIME_CONFIG: dict[str, Any] = deepcopy(DEFAULT_RUNTIME_CONFIG)
REFINED_RUNTIME_CONFIG["language_repair"] = False

STRUCTURED_PATCH_REFINED: dict[str, Any] = {
    "id": "structured-patch-refined",
    "name": "Gemma 4 Tuned Refined",
    "definition_revision": "structured-patch-refined-v2",
    "description": (
        "Refined Structured Patch workflow with required structural correction and no lexical "
        "identifier veto or whole-model language-repair pass."
    ),
    "runnable": True,
    "runtime_endpoint": "/api/runs",
    "runtime_note": (
        "Default workflow for new application runs. It preserves Unicode names, requires structural "
        "correction, and does not enforce lexical identifier or whole-model language heuristics."
    ),
    "runtime_config": deepcopy(REFINED_RUNTIME_CONFIG),
    "model_bindings": deepcopy(GEMINI_DEFAULT_MODEL_BINDINGS),
    "model_binding_slots": ["default"],
    "supported_providers": ["gemini", "nvidia_nim"],
    "required_capabilities": {"streaming": True, "json_response": True},
    "family": "structured_patch",
    "executor_id": HarnessExecutorId.STRUCTURED_PATCH_REFINED,
}

DIRECT_BASELINE_SCHEMA_ONLY_V1: dict[str, Any] = {
    "id": "direct-baseline-schema-only-v1",
    "name": "Direct Baseline - Schema Only",
    "definition_revision": "direct-baseline-schema-only-v1-20260616",
    "description": "Single-call direct JSON baseline using the legacy simple schema prompt.",
    "runnable": True,
    "runtime_endpoint": "/api/runs",
    "runtime_config": DIRECT_BASELINE_RUNTIME_CONFIG,
    "model_bindings": deepcopy(GEMINI_DEFAULT_MODEL_BINDINGS),
    "model_binding_slots": ["default"],
    "supported_providers": ["gemini", "codex", "nvidia_nim"],
    "required_capabilities": {"json_response": True},
    "family": "direct_baseline",
    "prompt_profile": "schema_only_v1",
    "executor_id": HarnessExecutorId.DIRECT_BASELINE,
}

DIRECT_BASELINE_STRUCTURED_DRAFT_WITH_ISSUES: dict[str, Any] = {
    "id": "direct-baseline-structured-draft-with-issues",
    "name": "Direct Baseline - Structured Draft With Issues",
    "definition_revision": "direct-baseline-structured-draft-with-issues-20260616",
    "description": "Single-call direct JSON baseline using the structured draft prompt with issue metadata.",
    "runnable": False,
    "family": "direct_baseline",
    "model_bindings": deepcopy(GEMINI_DEFAULT_MODEL_BINDINGS),
    "model_binding_slots": ["default"],
    "supported_providers": ["gemini", "codex", "nvidia_nim"],
    "required_capabilities": {"json_response": True},
    "prompt_profile": "structured_draft_with_issues",
    "executor_id": HarnessExecutorId.DIRECT_BASELINE,
}


def all_harness_definitions() -> list[HarnessDefinition]:
    raw_templates = (
        STRUCTURED_PATCH_REFINED,
        GEMMA4_TUNED_FINAL,
        DIRECT_BASELINE_SCHEMA_ONLY_V1,
        DIRECT_BASELINE_STRUCTURED_DRAFT_WITH_ISSUES,
    )
    return [HarnessDefinition.model_validate(deepcopy(template)) for template in raw_templates]


def all_harness_templates() -> list[dict[str, Any]]:
    return [definition.to_legacy_dict() for definition in all_harness_definitions()]


def list_harness_templates(*, include_internal: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "id": template["id"],
            "name": template["name"],
            "definition_revision": template.get("definition_revision", ""),
            "description": template["description"],
            "runnable": bool(template.get("runnable")),
            "family": template.get("family", ""),
            "executor_id": template.get("executor_id", ""),
            "prompt_profile": template.get("prompt_profile", ""),
            "runtime_endpoint": template.get("runtime_endpoint", ""),
            "runtime_note": template.get("runtime_note", ""),
            "runtime_config": deepcopy(template.get("runtime_config") or {}),
            "model_bindings": deepcopy(template.get("model_bindings") or {}),
            "model_binding_slots": deepcopy(template.get("model_binding_slots") or ["default"]),
            "supported_providers": deepcopy(template.get("supported_providers") or []),
            "required_capabilities": deepcopy(template.get("required_capabilities") or {}),
        }
        for template in all_harness_templates()
        if include_internal or bool(template.get("runnable"))
    ]


def get_harness_template(template_id: str) -> dict[str, Any] | None:
    definition = get_harness_definition(template_id)
    if definition is not None:
        return definition.to_legacy_dict()
    return None


def get_harness_definition(template_id: str) -> HarnessDefinition | None:
    for definition in all_harness_definitions():
        if definition.id == template_id:
            return definition.model_copy(deep=True)
    return None


def materialize_harness_run_spec(
    template_id: str,
    *,
    expected_definition_revision: str | None = None,
    runtime_config_override: dict[str, Any] | None = None,
    model_bindings: dict[str, Any] | None = None,
) -> EffectiveHarnessRunSpec:
    """Resolve a detached typed run specification without dispatching it."""

    definition = get_harness_definition(template_id)
    if definition is None:
        raise ValueError(f"Unknown harness definition: {template_id}")
    if (
        expected_definition_revision is not None
        and expected_definition_revision != definition.definition_revision
    ):
        raise HarnessDefinitionRevisionMismatchError(
            harness_id=template_id,
            expected=expected_definition_revision,
            actual=definition.definition_revision,
        )
    config_payload = definition.runtime_config.model_dump(mode="json")
    if runtime_config_override:
        config_payload.update(deepcopy(runtime_config_override))
    config_type = (
        StructuredPatchEffectiveConfig
        if definition.family == "structured_patch"
        else DirectBaselineEffectiveConfig
    )
    configured_bindings = config_payload.get("model_bindings") or definition.model_bindings
    resolved_bindings = deepcopy(model_bindings if model_bindings is not None else configured_bindings)
    config_payload["model_bindings"] = deepcopy(resolved_bindings)
    effective_config = config_type.model_validate(config_payload)
    return EffectiveHarnessRunSpec(
        harness_id=definition.id,
        definition_revision=definition.definition_revision,
        executor_id=definition.executor_id,
        family=definition.family,
        effective_config=effective_config,
        model_bindings=effective_config.model_bindings,
    ).detached_copy()


def available_tools() -> list[str]:
    return []


def available_deterministic_functions() -> list[str]:
    return []


__all__ = [
    "HarnessDefinitionRevisionMismatchError",
    "all_harness_definitions",
    "all_harness_templates",
    "available_deterministic_functions",
    "available_tools",
    "get_harness_definition",
    "get_harness_template",
    "list_harness_templates",
    "materialize_harness_run_spec",
]
