from __future__ import annotations

from typing import Any

from harnesses import get_harness_template


def inferred_runtime_harness_id(record: dict[str, Any]) -> str | None:
    runtime_harness_id = record.get("runtime_harness_id")
    if runtime_harness_id:
        return str(runtime_harness_id)
    return None


def inferred_runtime_harness_name(record: dict[str, Any]) -> str | None:
    runtime_harness_name = record.get("runtime_harness_name")
    if runtime_harness_name:
        return str(runtime_harness_name)
    runtime_harness_id = inferred_runtime_harness_id(record)
    if not runtime_harness_id:
        return None
    template = get_harness_template(runtime_harness_id) or {}
    return str(template.get("name") or runtime_harness_id)
