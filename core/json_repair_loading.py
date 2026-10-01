from __future__ import annotations

import json
from typing import Any

from core.json_repair_values import merge_duplicate_structured_json_value
from core.schemas import StructuredOutputError


class JsonObjectPairs(list):
    pass


def keep_json_object_pairs(pairs: list[tuple[str, Any]]) -> JsonObjectPairs:
    return JsonObjectPairs(pairs)


def repair_duplicate_structured_json_keys(value: Any, path: list[Any], reports: list[dict[str, Any]]) -> Any:
    if isinstance(value, JsonObjectPairs):
        repaired_object: dict[str, Any] = {}
        for key, raw_item in value:
            repaired_item = repair_duplicate_structured_json_keys(raw_item, path + [key], reports)
            if key not in repaired_object:
                repaired_object[key] = repaired_item
                continue
            merged_value, report = merge_duplicate_structured_json_value(
                key,
                repaired_object[key],
                repaired_item,
                path=path,
                current_object=repaired_object,
            )
            repaired_object[key] = merged_value
            reports.append(report)
        return repaired_object
    if isinstance(value, list):
        return [repair_duplicate_structured_json_keys(item, path + [index], reports) for index, item in enumerate(value)]
    return value


def load_structured_json_with_deterministic_repairs(raw_json: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pairs_payload = json.loads(raw_json, object_pairs_hook=keep_json_object_pairs)
    reports: list[dict[str, Any]] = []
    payload = repair_duplicate_structured_json_keys(pairs_payload, [], reports)
    if not isinstance(payload, dict):
        raise StructuredOutputError("Structured JSON output must be an object.")
    return payload, reports


def load_structured_patch_json_with_deterministic_repairs(raw_json: str) -> tuple[Any, list[dict[str, Any]]]:
    pairs_payload = json.loads(raw_json, object_pairs_hook=keep_json_object_pairs)
    reports: list[dict[str, Any]] = []
    payload = repair_duplicate_structured_json_keys(pairs_payload, [], reports)
    if not isinstance(payload, (dict, list)):
        raise StructuredOutputError("Structured patch operation output must be an object or array.")
    return payload, reports


__all__ = [
    "JsonObjectPairs",
    "keep_json_object_pairs",
    "load_structured_json_with_deterministic_repairs",
    "load_structured_patch_json_with_deterministic_repairs",
    "repair_duplicate_structured_json_keys",
]
