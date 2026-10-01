from __future__ import annotations

from core.json_repair_loading import (
    JsonObjectPairs,
    keep_json_object_pairs,
    load_structured_json_with_deterministic_repairs,
    load_structured_patch_json_with_deterministic_repairs,
    repair_duplicate_structured_json_keys,
)
from core.json_repair_reports import (
    DETERMINISTIC_REPAIR_KIND,
    deterministic_repair_report,
    format_json_repair_path,
    json_repair_target,
)
from core.json_repair_values import (
    merge_duplicate_attribute_arrays,
    merge_duplicate_identifier_arrays,
    merge_duplicate_string_arrays,
    merge_duplicate_structured_json_value,
)

__all__ = [
    "DETERMINISTIC_REPAIR_KIND",
    "JsonObjectPairs",
    "deterministic_repair_report",
    "format_json_repair_path",
    "json_repair_target",
    "keep_json_object_pairs",
    "load_structured_json_with_deterministic_repairs",
    "load_structured_patch_json_with_deterministic_repairs",
    "merge_duplicate_attribute_arrays",
    "merge_duplicate_identifier_arrays",
    "merge_duplicate_string_arrays",
    "merge_duplicate_structured_json_value",
    "repair_duplicate_structured_json_keys",
]
