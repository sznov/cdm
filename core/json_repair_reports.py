from __future__ import annotations

from typing import Any

DETERMINISTIC_REPAIR_KIND = "deterministicRepair"


def format_json_repair_path(path: list[Any]) -> str:
    rendered = "$"
    for part in path:
        if isinstance(part, int):
            rendered += f"[{part}]"
        else:
            rendered += f".{part}"
    return rendered


def json_repair_target(path: list[Any], current_object: dict[str, Any], key: str) -> str:
    entity_name = current_object.get("name")
    if key == "attributes" and isinstance(entity_name, str) and entity_name.strip():
        return f"{entity_name.strip()}.attributes"
    if key == "identifier" and isinstance(entity_name, str) and entity_name.strip():
        return f"{entity_name.strip()}.identifier"
    if key == "inherits_from" and isinstance(entity_name, str) and entity_name.strip():
        return f"{entity_name.strip()}.inherits_from"
    return format_json_repair_path(path + [key])


def deterministic_repair_report(target: str, summary: str, evidence: str) -> dict[str, Any]:
    return {
        "kind": DETERMINISTIC_REPAIR_KIND,
        "target": target,
        "summary": summary,
        "evidence": evidence,
        "options": [],
    }


__all__ = [
    "DETERMINISTIC_REPAIR_KIND",
    "deterministic_repair_report",
    "format_json_repair_path",
    "json_repair_target",
]
