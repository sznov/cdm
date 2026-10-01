from __future__ import annotations

import re
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)


STRUCTURED_ATTRIBUTE_TYPES = {"string", "int", "real", "bool", "date"}


STRUCTURED_ATTRIBUTE_TYPE_ALIASES = {
    "str": "string",
    "text": "string",
    "integer": "int",
    "number": "real",
    "float": "real",
    "boolean": "bool",
}


def normalize_structured_name(
    value: Any,
    *,
    style: str,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> Any:
    if style not in {"upper", "lower"}:
        raise ValueError(f"Unsupported structured-name style: {style!r}.")
    return name_policy.normalize(value, style=style)  # type: ignore[arg-type]


def normalize_structured_multiplicity(value: Any) -> Any:
    if value is None:
        return value
    text = str(value).strip()
    if text == "*":
        return "0..*"
    if text in {"0..1", "1", "0..*", "1..*"}:
        return text
    normalized = (
        text.lower()
        .replace(" ", "")
        .replace("…", "..")
        .replace("...", "..")
        .replace("∞", "*")
    )
    aliases = {
        "1..1": "1",
        "one": "1",
        "exactlyone": "1",
        "many": "0..*",
        "n": "0..*",
        "m": "0..*",
        "0..n": "0..*",
        "0..m": "0..*",
        "0..many": "0..*",
        "1..n": "1..*",
        "1..m": "1..*",
        "1..many": "1..*",
    }
    if normalized in aliases:
        return aliases[normalized]
    if re.fullmatch(r"[2-9]\d*\.\.\*", normalized):
        return "1..*"
    return value


def normalize_structured_attribute_type(raw_type: Any) -> str:
    value = str(raw_type or "string").strip().lower()
    value = STRUCTURED_ATTRIBUTE_TYPE_ALIASES.get(value, value)
    return value if value in STRUCTURED_ATTRIBUTE_TYPES else "string"


__all__ = [
    "STRUCTURED_ATTRIBUTE_TYPES",
    "STRUCTURED_ATTRIBUTE_TYPE_ALIASES",
    "normalize_structured_name",
    "normalize_structured_multiplicity",
    "normalize_structured_attribute_type",
]
