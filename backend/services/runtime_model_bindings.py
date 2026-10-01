from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from core.config_safety import selected_provider_endpoint_url
from core.model_bindings import (
    normalize_model_binding,
    validate_model_binding_capabilities,
    validate_model_bindings_security,
)
from harnesses.catalog import get_harness_definition


def validate_runtime_harness_model_bindings(
    runtime_harness_id: str,
    bindings: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    definition = get_harness_definition(runtime_harness_id)
    declared_slots = tuple(definition.model_binding_slots if definition else ("default",))
    supplied_slots = set(bindings)
    missing = set(declared_slots) - supplied_slots
    unexpected = supplied_slots - set(declared_slots)
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"unexpected: {', '.join(sorted(unexpected))}")
        raise HTTPException(
            status_code=400,
            detail=f"Model binding slots do not match the harness definition ({'; '.join(details)}).",
        )
    try:
        validate_model_bindings_security(bindings)
        normalized = {
            slot: normalize_model_binding(bindings[slot])
            for slot in declared_slots
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    for slot, binding in normalized.items():
        if not str(binding.get("model") or "").strip():
            raise HTTPException(status_code=400, detail=f"Choose a model for binding slot '{slot}'.")
        try:
            selected_provider_endpoint_url(
                str(binding.get("provider") or ""),
                binding.get("base_url"),
            )
            validate_model_binding_capabilities(
                binding,
                supported_providers=(definition.supported_providers if definition else None),
                required_capabilities=(definition.required_capabilities if definition else None),
                catalog_metadata_is_advisory=True,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return normalized


__all__ = ["validate_runtime_harness_model_bindings"]
