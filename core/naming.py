from __future__ import annotations

import re
import unicodedata


SERBIAN_ASCII_TRANSLATION = str.maketrans(
    {
        "č": "c",
        "ć": "c",
        "đ": "dj",
        "š": "s",
        "ž": "z",
        "Č": "C",
        "Ć": "C",
        "Đ": "Dj",
        "Š": "S",
        "Ž": "Z",
    }
)


def to_ascii_text(value: str) -> str:
    translated = value.translate(SERBIAN_ASCII_TRANSLATION)
    normalized = unicodedata.normalize("NFKD", translated)
    return normalized.encode("ascii", "ignore").decode("ascii")


def split_identifier_words(value: str) -> list[str]:
    ascii_value = to_ascii_text(value)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", ascii_value)
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", spaced)
    return re.findall(r"[A-Za-z0-9]+", spaced)


def to_upper_camel_ascii(value: str, *, fallback: str = "Entity") -> str:
    words = split_identifier_words(value)
    if not words:
        return fallback
    normalized_words = [word.lower() if word.isupper() else word for word in words]
    return "".join(word[:1].upper() + word[1:] for word in normalized_words)


def to_lower_camel_ascii(value: str, *, fallback: str = "value") -> str:
    upper_camel = to_upper_camel_ascii(value, fallback=fallback[:1].upper() + fallback[1:])
    return upper_camel[:1].lower() + upper_camel[1:]


def canonical_lookup_key(value: str) -> str:
    return "".join(split_identifier_words(value)).lower()

