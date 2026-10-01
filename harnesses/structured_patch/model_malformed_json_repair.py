from __future__ import annotations

import json
import re


def repair_missing_entities_array_close(extracted_json: str) -> str:
    """Repair a common model slip: placing relationships before closing entities."""
    entities_index = extracted_json.find('"entities"')
    relationships_index = extracted_json.find('"relationships"')
    if entities_index < 0 or relationships_index < 0 or relationships_index < entities_index:
        return extracted_json

    prefix = extracted_json[:relationships_index]
    stripped_prefix = prefix.rstrip()
    if not stripped_prefix.endswith(","):
        return extracted_json

    before_relationship_delimiter = stripped_prefix[:-1].rstrip()
    if before_relationship_delimiter.endswith("]"):
        return extracted_json

    delimiter_index = prefix.rfind(",")
    if delimiter_index < 0:
        return extracted_json
    return extracted_json[:delimiter_index] + "]," + extracted_json[delimiter_index + 1 :]


def repair_missing_relationship_object_closes(extracted_json: str) -> str:
    """Repair relationship objects whose target end is followed by the next object."""
    repaired = extracted_json
    for _ in range(4):
        next_repaired = re.sub(
            r'("target"\s*:\s*\{[^{}]*\})\s*,\s*(\{\s*"name"\s*:)',
            r"\1}, \2",
            repaired,
        )
        next_repaired = re.sub(
            r'("target"\s*:\s*\{[^{}]*\})\s*\]\s*(\}*)$',
            r"\1}]\2",
            next_repaired,
        )
        if next_repaired == repaired:
            break
        repaired = next_repaired
    return repaired


def repair_extra_trailing_object_closes(extracted_json: str) -> str:
    stripped = extracted_json.rstrip()
    trailing_whitespace = extracted_json[len(stripped) :]
    candidate = stripped
    for _ in range(3):
        if not candidate.endswith("}}"):
            break
        candidate = candidate[:-1].rstrip()
        try:
            json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return candidate + trailing_whitespace
    return extracted_json


def repair_missing_json_closers(extracted_json: str) -> str:
    stripped = extracted_json.rstrip()
    trailing_whitespace = extracted_json[len(stripped) :]
    stack: list[str] = []
    in_string = False
    escape = False

    for char in stripped:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in {"}", "]"}:
            if not stack or stack[-1] != char:
                return extracted_json
            stack.pop()

    if in_string or not stack:
        return extracted_json
    return stripped + "".join(reversed(stack)) + trailing_whitespace


def repair_malformed_structured_json(extracted_json: str) -> str:
    repaired = repair_missing_entities_array_close(extracted_json)
    repaired = repair_missing_relationship_object_closes(repaired)
    repaired = repair_extra_trailing_object_closes(repaired)
    repaired = repair_missing_json_closers(repaired)
    return repaired


__all__ = [
    "repair_extra_trailing_object_closes",
    "repair_malformed_structured_json",
    "repair_missing_entities_array_close",
    "repair_missing_json_closers",
    "repair_missing_relationship_object_closes",
]
