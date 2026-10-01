from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from core.json_repair_reports import deterministic_repair_report, json_repair_target


def merge_duplicate_attribute_arrays(
    existing: list[Any],
    incoming: list[Any],
    *,
    target: str,
) -> tuple[list[Any], dict[str, Any]]:
    merged: list[Any] = []
    by_name: dict[str, dict[str, Any]] = {}
    duplicate_names: list[str] = []
    added_names: list[str] = []

    for source_index, attribute in enumerate([*existing, *incoming], start=1):
        if not isinstance(attribute, dict):
            if attribute not in merged:
                merged.append(attribute)
            continue
        name = str(attribute.get("name") or "").strip()
        if not name:
            if attribute not in merged:
                merged.append(deepcopy(attribute))
            continue
        if name not in by_name:
            attribute_copy = deepcopy(attribute)
            by_name[name] = attribute_copy
            merged.append(attribute_copy)
            if source_index > len(existing):
                added_names.append(name)
            continue

        duplicate_names.append(name)
        previous = by_name[name]
        previous_type = str(previous.get("type") or "").strip()
        incoming_type = str(attribute.get("type") or "").strip()
        if previous_type and incoming_type and previous_type != incoming_type:
            raise ValueError(
                f"Duplicate JSON key 'attributes' at {target} cannot be safely repaired because "
                f"attribute '{name}' has conflicting types '{previous_type}' and '{incoming_type}'."
            )
        if not previous_type and incoming_type:
            previous["type"] = incoming_type
        for attr_key, attr_value in attribute.items():
            if attr_key not in previous:
                previous[attr_key] = deepcopy(attr_value)

    evidence_parts = [
        f"duplicate JSON key 'attributes' merged {len(existing)} + {len(incoming)} entries into {len(merged)} unique entries"
    ]
    if duplicate_names:
        evidence_parts.append(f"deduped attributes: {', '.join(sorted(set(duplicate_names)))}")
    if added_names:
        evidence_parts.append(f"added attributes from later block: {', '.join(sorted(set(added_names)))}")
    report = deterministic_repair_report(
        target,
        f"Merged duplicate attributes arrays at {target}.",
        "; ".join(evidence_parts) + ".",
    )
    return merged, report


def merge_duplicate_identifier_arrays(
    existing: list[Any],
    incoming: list[Any],
    *,
    target: str,
) -> tuple[list[Any], dict[str, Any]]:
    if existing == incoming:
        return existing, deterministic_repair_report(
            target,
            f"Removed identical duplicate identifier array at {target}.",
            "duplicate JSON key 'identifier' repeated the same identifier parts.",
        )
    if not existing and incoming:
        return incoming, deterministic_repair_report(
            target,
            f"Kept non-empty duplicate identifier array at {target}.",
            "duplicate JSON key 'identifier' had one empty block and one non-empty block.",
        )
    if existing and not incoming:
        return existing, deterministic_repair_report(
            target,
            f"Kept non-empty duplicate identifier array at {target}.",
            "duplicate JSON key 'identifier' had one non-empty block and one empty block.",
        )
    raise ValueError(
        f"Duplicate JSON key 'identifier' at {target} is ambiguous; competing identifier arrays were not merged."
    )


def merge_duplicate_string_arrays(
    key: str,
    existing: list[Any],
    incoming: list[Any],
    *,
    target: str,
) -> tuple[list[Any], dict[str, Any]]:
    merged: list[Any] = []
    seen: set[str] = set()
    for value in [*existing, *incoming]:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(value)
    return merged, deterministic_repair_report(
        target,
        f"Merged duplicate {key} arrays at {target}.",
        f"duplicate JSON key '{key}' merged {len(existing)} + {len(incoming)} entries into {len(merged)} unique entries.",
    )


def merge_duplicate_structured_json_value(
    key: str,
    existing: Any,
    incoming: Any,
    *,
    path: list[Any],
    current_object: dict[str, Any],
) -> tuple[Any, dict[str, Any]]:
    target = json_repair_target(path, current_object, key)
    if existing == incoming:
        return existing, deterministic_repair_report(
            target,
            f"Removed identical duplicate JSON key '{key}'.",
            f"duplicate JSON key '{key}' had identical values, so the first value was kept.",
        )
    if key == "attributes" and isinstance(existing, list) and isinstance(incoming, list):
        return merge_duplicate_attribute_arrays(existing, incoming, target=target)
    if key == "identifier" and isinstance(existing, list) and isinstance(incoming, list):
        return merge_duplicate_identifier_arrays(existing, incoming, target=target)
    if key in {"issues", "inherits_from"} and isinstance(existing, list) and isinstance(incoming, list):
        return merge_duplicate_string_arrays(key, existing, incoming, target=target)
    raise ValueError(
        f"Duplicate JSON key '{key}' at {target} cannot be safely repaired because the values differ."
    )


__all__ = [
    "merge_duplicate_attribute_arrays",
    "merge_duplicate_identifier_arrays",
    "merge_duplicate_string_arrays",
    "merge_duplicate_structured_json_value",
]
