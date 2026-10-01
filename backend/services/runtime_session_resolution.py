from __future__ import annotations

from copy import deepcopy

from fastapi import HTTPException

from backend.api.models import SessionCreateRequest
from backend.services.runtime_harness_spec import materialized_runtime_harness_spec
from backend.services.runtime_model_bindings import validate_runtime_harness_model_bindings
from harnesses.catalog import HarnessDefinitionRevisionMismatchError, get_harness_definition
from harnesses.contracts import EffectiveHarnessRunSpec


def materialized_session_harness_spec(request: SessionCreateRequest) -> EffectiveHarnessRunSpec:
    definition = get_harness_definition(request.runtime_harness_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Runtime harness not found.")
    if not definition.runnable:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Runtime harness '{request.runtime_harness_id}' is not available in the "
                "browser application. Use its script entry point instead."
            ),
        )
    bindings = (
        {
            slot: binding.model_dump(mode="json", exclude_unset=True)
            for slot, binding in request.model_bindings.items()
        }
        if request.model_bindings is not None
        else definition.model_dump(mode="json").get("model_bindings")
        or definition.runtime_config.model_dump(mode="json").get("model_bindings")
    )
    if not isinstance(bindings, dict):
        raise HTTPException(status_code=400, detail="Choose a model first.")
    bindings = validate_runtime_harness_model_bindings(request.runtime_harness_id, bindings)
    try:
        return materialized_runtime_harness_spec(
            runtime_harness_id=request.runtime_harness_id,
            harness_definition_revision=request.harness_definition_revision,
            harness_runtime_config=request.harness_runtime_config,
            model_bindings=deepcopy(bindings),
        )
    except HarnessDefinitionRevisionMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = ["materialized_session_harness_spec"]
