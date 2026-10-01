from __future__ import annotations

import re
from typing import Any

from core.naming import split_identifier_words, to_ascii_text


def structured_concept_key(value: str) -> str:
    return "".join(split_identifier_words(value)).lower()


def string_distance_at_most_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) > len(right):
        left, right = right, left
    index_left = 0
    index_right = 0
    edits = 0
    while index_left < len(left) and index_right < len(right):
        if left[index_left] == right[index_right]:
            index_left += 1
            index_right += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(left) == len(right):
            index_left += 1
        index_right += 1
    return True


def spec_word_set(specification: str) -> set[str]:
    return {
        word.lower()
        for word in re.findall(r"[A-Za-z0-9]+", to_ascii_text(specification))
        if any(char.isalpha() for char in word)
    }


def repair_word_supported_by_spec(word: str, spec_words: set[str]) -> bool:
    normalized = word.lower()
    if normalized in spec_words:
        return True
    if len(normalized) < 4:
        return False
    if any(
        4 <= len(candidate)
        and max(len(normalized), len(candidate)) <= 5
        and string_distance_at_most_one(normalized, candidate)
        for candidate in spec_words
    ):
        return True
    prefix_length = 4 if len(normalized) >= 5 else len(normalized)
    prefix = normalized[:prefix_length]
    return any(
        len(candidate) >= prefix_length
        and (candidate.startswith(prefix) or normalized.startswith(candidate[:prefix_length]))
        for candidate in spec_words
    )


def repair_name_support(
    name: str,
    *,
    spec_words: set[str],
) -> dict[str, Any]:
    words = [
        word.lower()
        for word in split_identifier_words(name)
        if word
    ]
    support_words = [word for word in words if len(word) > 2] or words
    unsupported = [word for word in support_words if not repair_word_supported_by_spec(word, spec_words)]
    return {
        "words": words,
        "support_words": support_words,
        "unsupported_words": unsupported,
        "supported": not unsupported,
    }


def rename_adds_only_short_suffix(old: str, new: str) -> bool:
    old_words = [word.lower() for word in split_identifier_words(old)]
    new_words = [word.lower() for word in split_identifier_words(new)]
    if not old_words or len(new_words) <= len(old_words):
        return False
    if new_words[: len(old_words)] != old_words:
        return False
    added_words = new_words[len(old_words) :]
    return bool(added_words) and all(1 < len(word) <= 4 for word in added_words)


def supported_words_in_name(name: str, *, spec_words: set[str]) -> list[str]:
    support = repair_name_support(name, spec_words=spec_words)
    unsupported = set(support["unsupported_words"])
    return [word for word in support["support_words"] if word not in unsupported]


__all__ = [
    "structured_concept_key",
    "string_distance_at_most_one",
    "spec_word_set",
    "repair_word_supported_by_spec",
    "repair_name_support",
    "rename_adds_only_short_suffix",
    "supported_words_in_name",
]
