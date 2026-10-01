from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from core.naming import split_identifier_words, to_lower_camel_ascii, to_upper_camel_ascii
from core.schemas import StructuredModel


NameStyle = Literal["upper", "lower"]


class StructuredNamePolicyId(StrEnum):
    LEGACY_ASCII_V1 = "legacy_ascii_v1"
    UNICODE_NFKC_V1 = "unicode_nfkc_v1"


class StructuredNamePolicyError(ValueError):
    pass


def _character_kind(character: str) -> str:
    return unicodedata.category(character)[:1]


def _reject_unsafe_characters(value: str) -> None:
    for character in value:
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Cs"}:
            raise StructuredNamePolicyError(
                f"Structured names cannot contain Unicode {category} characters."
            )


def _unicode_identifier_units(value: str) -> list[list[str]]:
    units: list[list[str]] = []
    for character in value:
        kind = _character_kind(character)
        if kind in {"L", "N"}:
            units.append([character])
        elif kind == "M":
            if not units:
                raise StructuredNamePolicyError(
                    "Structured names cannot contain a detached Unicode combining mark."
                )
            units[-1].append(character)
    return units


def _unit_case(unit: list[str]) -> str:
    for character in unit:
        if character.lower() != character.upper():
            if character.isupper() or character.istitle():
                return "upper"
            if character.islower():
                return "lower"
    return "uncased"


def _split_unicode_segment(segment: str) -> list[str]:
    units = _unicode_identifier_units(segment)
    if not units:
        return []
    words: list[list[list[str]]] = [[]]
    for index, unit in enumerate(units):
        current_case = _unit_case(unit)
        previous_case = _unit_case(units[index - 1]) if index else "uncased"
        next_case = _unit_case(units[index + 1]) if index + 1 < len(units) else "uncased"
        boundary = index > 0 and (
            (previous_case == "lower" and current_case == "upper")
            or (previous_case == "uncased" and current_case == "upper")
            or (
                previous_case == "upper"
                and current_case == "upper"
                and next_case == "lower"
            )
        )
        if boundary:
            words.append([])
        words[-1].append(unit)
    return ["".join("".join(unit) for unit in word) for word in words if word]


def _unicode_identifier_words(value: str) -> list[str]:
    words: list[str] = []
    segment: list[str] = []
    for character in value:
        kind = _character_kind(character)
        if kind in {"L", "M", "N"}:
            segment.append(character)
            continue
        if segment:
            words.extend(_split_unicode_segment("".join(segment)))
            segment = []
    if segment:
        words.extend(_split_unicode_segment("".join(segment)))
    return words


def _change_first_cased_character(value: str, *, upper: bool) -> str:
    for index, character in enumerate(value):
        if character.lower() == character.upper():
            continue
        # title(), unlike upper(), keeps expanding mappings camel-stable:
        # German ß becomes "Ss" rather than "SS" and Greek titlecase is
        # retained as titlecase on the next normalization pass.
        replacement = character.title() if upper else character.lower()
        return value[:index] + replacement + value[index + 1 :]
    return value


def _camel_word(value: str, *, upper: bool) -> str:
    normalized = value.lower() if value.isupper() else value
    return _change_first_cased_character(normalized, upper=upper)


def _normalize_unicode_name(value: Any, *, style: NameStyle) -> Any:
    if not isinstance(value, str):
        return value
    normalized = unicodedata.normalize("NFKC", value.strip())
    _reject_unsafe_characters(normalized)
    words = _unicode_identifier_words(normalized)
    if not words:
        raise StructuredNamePolicyError(
            "Structured names must contain at least one Unicode letter, combining mark, or number."
        )
    if style == "upper":
        result = "".join(_camel_word(word, upper=True) for word in words)
    else:
        result = "".join(
            _camel_word(word, upper=index > 0)
            for index, word in enumerate(words)
        )
    # Unicode case conversion can itself produce decomposed text (for example
    # Turkish dotted I), so the persisted spelling needs one final NFKC pass.
    return unicodedata.normalize("NFKC", result)


@dataclass(frozen=True, slots=True)
class StructuredNamePolicy:
    policy_id: StructuredNamePolicyId

    @property
    def preserves_unicode(self) -> bool:
        return self.policy_id == StructuredNamePolicyId.UNICODE_NFKC_V1

    def normalize(self, value: Any, *, style: NameStyle) -> Any:
        if self.policy_id == StructuredNamePolicyId.LEGACY_ASCII_V1:
            if not isinstance(value, str):
                return value
            stripped = value.strip()
            if not stripped or not split_identifier_words(stripped):
                return value
            if style == "upper":
                return to_upper_camel_ascii(stripped)
            return to_lower_camel_ascii(stripped)
        return _normalize_unicode_name(value, style=style)

    def comparison_key(self, value: Any) -> str:
        text = str(value or "")
        if self.policy_id == StructuredNamePolicyId.LEGACY_ASCII_V1:
            return text
        return unicodedata.normalize("NFKC", text).casefold()

    def names_equal(self, left: Any, right: Any) -> bool:
        return self.comparison_key(left) == self.comparison_key(right)

    def validate_model_names(self, model: StructuredModel) -> None:
        if not self.preserves_unicode:
            return

        def validated_key(value: str, *, style: NameStyle) -> str:
            normalized = _normalize_unicode_name(value, style=style)
            if normalized != value:
                raise StructuredNamePolicyError(
                    f"Structured name {value!r} is not normalized under {self.policy_id.value}."
                )
            return self.comparison_key(value)

        entity_keys: dict[str, str] = {}
        for entity in model.entities:
            key = validated_key(entity.name, style="upper")
            if key in entity_keys and entity_keys[key] != entity.name:
                raise StructuredNamePolicyError(
                    f"Entity names {entity_keys[key]!r} and {entity.name!r} collide after NFKC case-folding."
                )
            entity_keys[key] = entity.name

            attribute_keys: dict[str, str] = {}
            for attribute in entity.attributes:
                attribute_key = validated_key(attribute.name, style="lower")
                if attribute_key in attribute_keys and attribute_keys[attribute_key] != attribute.name:
                    raise StructuredNamePolicyError(
                        f"Attribute names {attribute_keys[attribute_key]!r} and {attribute.name!r} "
                        f"collide on entity {entity.name!r} after NFKC case-folding."
                    )
                attribute_keys[attribute_key] = attribute.name

        relationship_keys: dict[str, str] = {}
        for relationship in model.relationships:
            if relationship.name:
                key = validated_key(relationship.name, style="lower")
                if key in relationship_keys and relationship_keys[key] != relationship.name:
                    raise StructuredNamePolicyError(
                        f"Relationship names {relationship_keys[key]!r} and {relationship.name!r} "
                        "collide after NFKC case-folding."
                    )
                relationship_keys[key] = relationship.name
            for end in (relationship.source, relationship.target):
                if end.role:
                    validated_key(end.role, style="lower")


LEGACY_ASCII_NAME_POLICY = StructuredNamePolicy(StructuredNamePolicyId.LEGACY_ASCII_V1)
UNICODE_NFKC_NAME_POLICY = StructuredNamePolicy(StructuredNamePolicyId.UNICODE_NFKC_V1)


__all__ = [
    "LEGACY_ASCII_NAME_POLICY",
    "NameStyle",
    "StructuredNamePolicy",
    "StructuredNamePolicyError",
    "StructuredNamePolicyId",
    "UNICODE_NFKC_NAME_POLICY",
]
