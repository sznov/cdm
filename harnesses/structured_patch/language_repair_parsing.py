from __future__ import annotations

from core.json_parsing import parse_json_object_output
from core.schemas import StructuredOutputError


def parse_structured_language_repair_output(raw_output: str) -> list[dict[str, str]]:
    payload = parse_json_object_output(raw_output, label="Structured language repair")
    raw_renames = payload.get("renames", [])
    if raw_renames is None:
        raw_renames = []
    if not isinstance(raw_renames, list):
        raise StructuredOutputError("Structured language repair output must contain a renames list.")
    renames: list[dict[str, str]] = []
    for index, item in enumerate(raw_renames, start=1):
        if not isinstance(item, dict):
            continue
        old = str(item.get("old") or "").strip()
        new = str(item.get("new") or "").strip()
        kind = str(item.get("kind") or "").strip()
        if not old or not new or not kind:
            continue
        renames.append(
            {
                "kind": kind,
                "entity": str(item.get("entity") or "").strip(),
                "old": old,
                "new": new,
                "reason": str(item.get("reason") or f"Rename suggestion {index}.").strip(),
            }
        )
    return renames


__all__ = ["parse_structured_language_repair_output"]
