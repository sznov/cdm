from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.api.settings import RUN_TRACE_FILENAME
from backend.persistence.run_trace import load_trace
from core.schemas import StructuredModel
from harnesses.structured_patch.name_policy import StructuredNamePolicy


def _mapped_name(
    value: str,
    mapping: dict[Any, Any],
    *,
    name_policy: StructuredNamePolicy,
) -> str:
    direct = mapping.get(value)
    if isinstance(direct, str):
        return direct
    if name_policy.preserves_unicode:
        key = name_policy.comparison_key(value)
        for candidate, replacement in mapping.items():
            if isinstance(candidate, str) and name_policy.comparison_key(candidate) == key:
                return str(replacement)
    return value


def structured_language_rename_maps_for_run(run_dir: Path) -> dict[str, Any]:
    trace_path = run_dir / RUN_TRACE_FILENAME
    maps: dict[str, Any] = {
        "entities": {},
        "relationships": {},
        "attributes": {},
    }
    if not trace_path.is_file():
        return maps
    try:
        trace = load_trace(trace_path)
    except Exception:
        return maps
    for entry in trace:
        if entry.get("event") != "structured_language_repair_applied":
            continue
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        renames = payload.get("applied_renames")
        if not isinstance(renames, list):
            renames = payload.get("accepted_renames")
        if not isinstance(renames, list):
            continue
        for rename in renames:
            if not isinstance(rename, dict):
                continue
            if rename.get("applied") is False:
                continue
            kind = str(rename.get("kind") or "").strip()
            old = str(rename.get("old") or "").strip()
            new = str(rename.get("new") or "").strip()
            if not kind or not old or not new or old == new:
                continue
            if kind == "entity":
                maps["entities"][old] = new
            elif kind == "relationship":
                maps["relationships"][old] = new
            elif kind == "attribute":
                entity = str(rename.get("entity") or "").strip()
                if entity:
                    maps["attributes"][(maps["entities"].get(entity, entity), old)] = new
                    maps["attributes"][(entity, old)] = new
    return maps


def rebase_decision_operation_for_current_model(
    operation: dict[str, Any],
    model: StructuredModel,
    rename_maps: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy,
) -> dict[str, Any]:
    rebased = deepcopy(operation)
    entity_renames = rename_maps.get("entities") if isinstance(rename_maps.get("entities"), dict) else {}
    relationship_renames = rename_maps.get("relationships") if isinstance(rename_maps.get("relationships"), dict) else {}
    attribute_renames = rename_maps.get("attributes") if isinstance(rename_maps.get("attributes"), dict) else {}

    if isinstance(rebased.get("entity"), str):
        rebased["entity"] = _mapped_name(
            rebased["entity"], entity_renames, name_policy=name_policy
        )
    for endpoint_name in ("source", "target"):
        endpoint = rebased.get(endpoint_name)
        if isinstance(endpoint, dict) and isinstance(endpoint.get("entity"), str):
            endpoint["entity"] = _mapped_name(
                endpoint["entity"], entity_renames, name_policy=name_policy
            )
    if isinstance(rebased.get("parent"), str):
        rebased["parent"] = _mapped_name(
            rebased["parent"], entity_renames, name_policy=name_policy
        )
    if isinstance(rebased.get("old"), str):
        if rebased.get("op") == "renameRelationship":
            rebased["old"] = _mapped_name(
                rebased["old"], relationship_renames, name_policy=name_policy
            )
        elif rebased.get("op") == "renameEntity":
            rebased["old"] = _mapped_name(
                rebased["old"], entity_renames, name_policy=name_policy
            )
    if isinstance(rebased.get("name"), str) and rebased.get("op") in {"removeRelationship", "renameRelationship"}:
        rebased["name"] = _mapped_name(
            rebased["name"], relationship_renames, name_policy=name_policy
        )

    if rebased.get("op") != "setIdentifier":
        return rebased

    entity_name = str(rebased.get("entity") or "").strip()
    entity = next(
        (item for item in model.entities if name_policy.names_equal(item.name, entity_name)),
        None,
    )
    if entity is None:
        return rebased
    current_attribute_names = {attribute.name for attribute in entity.attributes}
    current_relationship_names = {relationship.name for relationship in model.relationships}
    parts = rebased.get("parts") if isinstance(rebased.get("parts"), list) else rebased.get("identifier")
    if not isinstance(parts, list):
        return rebased
    for part in parts:
        if not isinstance(part, dict):
            continue
        ref = str(part.get("ref") or "").strip()
        if not ref:
            continue
        if part.get("kind") == "attribute" and not any(
            name_policy.names_equal(ref, current) for current in current_attribute_names
        ):
            replacement = attribute_renames.get((entity_name, ref))
            if replacement and any(
                name_policy.names_equal(replacement, current) for current in current_attribute_names
            ):
                part["ref"] = replacement
        elif part.get("kind") == "relationship" and not any(
            name_policy.names_equal(ref, current) for current in current_relationship_names
        ):
            replacement = _mapped_name(ref, relationship_renames, name_policy=name_policy)
            if replacement != ref and any(
                name_policy.names_equal(replacement, current) for current in current_relationship_names
            ):
                part["ref"] = replacement
    return rebased


def update_decision_patch_operation_references(
    patch: dict[str, Any],
    option_id: str,
    original_operation: dict[str, Any],
    rebased_operation: dict[str, Any],
) -> None:
    if patch.get("operation") == original_operation:
        patch["operation"] = rebased_operation
    options = patch.get("options")
    if not isinstance(options, list):
        return
    for option in options:
        if not isinstance(option, dict):
            continue
        is_selected = str(option.get("id") or "").strip() == option_id
        if is_selected or option.get("operation") == original_operation:
            if isinstance(option.get("operation"), dict):
                option["operation"] = rebased_operation
        if is_selected or option.get("patch") == original_operation:
            if isinstance(option.get("patch"), dict):
                option["patch"] = rebased_operation


__all__ = [
    "rebase_decision_operation_for_current_model",
    "structured_language_rename_maps_for_run",
    "update_decision_patch_operation_references",
]
