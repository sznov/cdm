from __future__ import annotations

from core.naming import split_identifier_words
from harnesses.structured_patch.language_word_support import string_distance_at_most_one, structured_concept_key


def compare_name_tokens(value: str) -> tuple[str, ...]:
    return tuple(word.lower() for word in split_identifier_words(value) if word)


def compare_tokens_match(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < 5:
        return False
    return string_distance_at_most_one(left, right)


def compare_name_similarity(actual_name: str, reference_name: str) -> float:
    actual_key = structured_concept_key(actual_name)
    reference_key = structured_concept_key(reference_name)
    if not actual_key or not reference_key:
        return 0.0
    if actual_key == reference_key:
        return 1.0

    actual_tokens = compare_name_tokens(actual_name)
    reference_tokens = compare_name_tokens(reference_name)
    if not actual_tokens or not reference_tokens:
        return 0.0

    def matched_count(left_tokens: tuple[str, ...], right_tokens: tuple[str, ...]) -> int:
        remaining = list(right_tokens)
        matched = 0
        for left in left_tokens:
            for index, right in enumerate(remaining):
                if compare_tokens_match(left, right):
                    matched += 1
                    remaining.pop(index)
                    break
        return matched

    actual_matched = matched_count(actual_tokens, reference_tokens)
    reference_matched = matched_count(reference_tokens, actual_tokens)
    actual_coverage = actual_matched / len(actual_tokens)
    reference_coverage = reference_matched / len(reference_tokens)
    coverage = (actual_coverage + reference_coverage) / 2

    # A one-token prediction can be a legitimate short label for a longer concept,
    # but keep it below exact/fuller matches.
    if min(len(actual_tokens), len(reference_tokens)) == 1:
        if actual_coverage == 1.0 or reference_coverage == 1.0:
            return max(coverage, 0.64)
        return 0.0
    return coverage


__all__ = [
    "compare_name_similarity",
    "compare_name_tokens",
    "compare_tokens_match",
]
