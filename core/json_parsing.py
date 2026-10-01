from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from core.schemas import StructuredOutputError


def format_validation_error(exc: ValidationError) -> str:
    issues: list[str] = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(part) for part in error.get("loc", [])) or "root"
        issues.append(f"{location}: {error.get('msg', 'Invalid value')}")

    return "; ".join(issues) or "Invalid structured JSON output."


def extract_json_object(raw_output: str) -> str:
    stripped = raw_output.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    if start < 0:
        return stripped

    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(stripped[start:], start=start):
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
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]

    return stripped[start:]


def reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    seen: set[str] = set()
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"Duplicate JSON key: {key}")
        seen.add(key)
        payload[key] = value
    return payload


def strip_model_thought_blocks(raw_output: str) -> str:
    without_thought = re.sub(r"<thought\b[^>]*>.*?</thought>", "", raw_output, flags=re.IGNORECASE | re.DOTALL)
    without_think = re.sub(r"<think\b[^>]*>.*?</think>", "", without_thought, flags=re.IGNORECASE | re.DOTALL)
    return re.sub(r"<(?:thought|think)\b[^>]*>.*$", "", without_think, flags=re.IGNORECASE | re.DOTALL)


def iter_balanced_json_objects(raw_output: str) -> list[str]:
    candidates: list[str] = []
    for start, char in enumerate(raw_output):
        if char != "{":
            continue
        depth = 0
        in_string = False
        escape = False
        for index, current in enumerate(raw_output[start:], start=start):
            if in_string:
                if escape:
                    escape = False
                elif current == "\\":
                    escape = True
                elif current == '"':
                    in_string = False
                continue

            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(raw_output[start : index + 1])
                    break
    return candidates


def parse_json_object_output(raw_output: str, *, label: str) -> dict[str, Any]:
    stripped = strip_model_thought_blocks(raw_output)
    candidates = iter_balanced_json_objects(stripped)
    if not candidates:
        candidates = iter_balanced_json_objects(raw_output)
    parsed_errors: list[str] = []
    for candidate in sorted(candidates, key=len, reverse=True):
        try:
            payload = json.loads(candidate, object_pairs_hook=reject_duplicate_json_keys)
        except (json.JSONDecodeError, ValueError) as exc:
            parsed_errors.append(str(exc))
            continue
        if isinstance(payload, dict):
            return payload
    try:
        payload = json.loads(extract_json_object(stripped), object_pairs_hook=reject_duplicate_json_keys)
    except (json.JSONDecodeError, ValueError) as exc:
        extra = f" Candidate errors: {'; '.join(parsed_errors[:3])}." if parsed_errors else ""
        if isinstance(exc, json.JSONDecodeError):
            location = f"{exc.msg} at line {exc.lineno} column {exc.colno}"
        else:
            location = str(exc)
        raise StructuredOutputError(
            f"{label} JSON parsing failed. {location}.{extra}"
        ) from exc
    if not isinstance(payload, dict):
        raise StructuredOutputError(f"{label} output must be a JSON object.")
    return payload


__all__ = [
    "extract_json_object",
    "format_validation_error",
    "iter_balanced_json_objects",
    "parse_json_object_output",
    "reject_duplicate_json_keys",
    "strip_model_thought_blocks",
]
