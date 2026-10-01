from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.api.models import HarnessRuntimeConfigOverrides
from core.model_bindings import normalize_model_bindings
from harnesses.catalog import materialize_harness_run_spec
from harnesses.contracts import EffectiveHarnessRunSpec, RuntimeModelBinding


def workflow_runtime_override(
    configured: HarnessRuntimeConfigOverrides | dict[str, Any] | None,
) -> dict[str, Any]:
    if configured is None:
        return {}
    if isinstance(configured, HarnessRuntimeConfigOverrides):
        return configured.detached_override()
    return HarnessRuntimeConfigOverrides.model_validate(configured).detached_override()


def workflow_runtime_config_from_effective(spec: EffectiveHarnessRunSpec) -> dict[str, Any]:
    payload = spec.effective_config.model_dump(mode="json")
    return HarnessRuntimeConfigOverrides.model_validate(
        {
            field_name: payload[field_name]
            for field_name in HarnessRuntimeConfigOverrides.model_fields
            if field_name in payload
        }
    ).detached_override()


def materialized_runtime_harness_spec(
    *,
    runtime_harness_id: str,
    harness_definition_revision: str | None,
    harness_runtime_config: HarnessRuntimeConfigOverrides | dict[str, Any] | None,
    model_bindings: dict[str, RuntimeModelBinding] | dict[str, Any],
) -> EffectiveHarnessRunSpec:
    """Materialize one API run while preserving the recorded legacy spec shape.

    API callers provide workflow overrides and model bindings through separate,
    non-overlapping fields.  The effective harness contract still carries the
    historical provider projections because legacy protocol snapshots
    must retain their exact serialized shape.
    """

    raw_bindings = {
        slot: (
            binding.model_dump(mode="json", exclude_unset=True)
            if isinstance(binding, RuntimeModelBinding)
            else deepcopy(binding)
        )
        for slot, binding in model_bindings.items()
    }
    bindings = normalize_model_bindings(raw_bindings)
    default_binding = bindings["default"]
    override = workflow_runtime_override(harness_runtime_config)
    override.update(
        provider=default_binding["provider"],
        model=default_binding["model"],
        model_bindings=deepcopy(bindings),
        num_predict=default_binding.get("max_completion_tokens"),
        temperature=default_binding.get("temperature"),
        top_p=default_binding.get("top_p"),
        timeout_seconds=default_binding.get("timeout_seconds") or 600.0,
    )
    if default_binding.get("base_url") is not None:
        override["gemini_base_url"] = default_binding["base_url"]
    return materialize_harness_run_spec(
        runtime_harness_id,
        runtime_config_override=override,
        model_bindings=bindings,
        expected_definition_revision=harness_definition_revision,
    ).detached_copy()


__all__ = [
    "materialized_runtime_harness_spec",
    "workflow_runtime_config_from_effective",
    "workflow_runtime_override",
]
