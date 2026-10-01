from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.schemas import StructuredModel
from harnesses.structured_patch.patch_signatures import normalized_operation_signature_payload
from harnesses.structured_patch.patch_operation_apply import apply_structured_patch_operation
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    UNICODE_NFKC_NAME_POLICY,
    StructuredNamePolicy,
)


CorrectionOperationGuard = Callable[[dict[str, Any], StructuredModel, str], str | None]


@dataclass(frozen=True, slots=True)
class CorrectionPhasePolicy:
    """Explicit behavior contract for the legacy and refined protocols."""

    policy_id: str
    operation_guard: CorrectionOperationGuard | None
    refined: bool
    success_stop_reason: str
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY


def _spec_guard_words(value: str) -> list[str]:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return re.findall(r"[a-z0-9]+", text.lower())


def _spec_guard_word_matches(left: str, right: str) -> bool:
    if left == right:
        return True
    if len(left) < 5 or len(right) < 5:
        return False
    return left.startswith(right) or right.startswith(left)


def specification_appears_to_state_identifier(
    specification: str,
    entity_name: str,
    attribute_name: str,
) -> bool:
    """Detect only clear, unnegated clause-local identifier evidence.

    This is intentionally a narrow safety heuristic, not a natural-language
    parser.  Ambiguous or contradictory prose is allowed through so a required
    correction is not blocked by a guessed meaning.
    """
    entity_words = [word for word in _spec_guard_words(entity_name) if len(word) >= 3]
    attribute_words = _spec_guard_words(attribute_name)
    if str(attribute_name or "").strip().lower() == "id":
        attribute_words.append("id")
    attribute_words = [word for word in attribute_words if word]
    if not entity_words or not attribute_words:
        return False

    # Merely mentioning an entity and one of its fields is not evidence that
    # the field identifies the entity.  Keep the deliberately conservative
    # lexical guard, but require an identifier cue unless the referenced field
    # is itself conventionally named ``id``/``identifier``.  This lets an
    # explicit correction remove, for example, an obsolete email attribute.
    direct_identifier_name = any(
        word == "id" or word.startswith("identif")
        for word in attribute_words
    )
    negators = {"ne", "never", "nije", "nisu", "no", "not", "without"}
    clauses = re.split(
        r"[.!?;\n]+|\bwhile\b|\bwhereas\b|\band\s+(?:each|every)\b",
        str(specification or ""),
        flags=re.IGNORECASE,
    )
    for clause in clauses:
        spec_words = _spec_guard_words(clause)
        if not spec_words or any(
            word in negators or word == "non" or word.startswith("nonunique")
            for word in spec_words
        ):
            continue
        entity_positions = [
            index
            for index, word in enumerate(spec_words)
            if any(_spec_guard_word_matches(word, entity_word) for entity_word in entity_words)
        ]
        attribute_positions = [
            index
            for index, word in enumerate(spec_words)
            if any(_spec_guard_word_matches(word, attribute_word) for attribute_word in attribute_words)
        ]
        cue_positions = [
            index
            for index, word in enumerate(spec_words)
            if (
                word.startswith("identif")
                or word.startswith("uniqu")
                or word.startswith("jedinstven")
                or word.startswith("kljuc")
                or word in {"key", "keys", "primary"}
            )
        ]
        for entity_index in entity_positions:
            for attribute_index in attribute_positions:
                if abs(entity_index - attribute_index) > 24:
                    continue
                if direct_identifier_name:
                    return True
                if any(
                    max(
                        abs(cue_index - entity_index),
                        abs(cue_index - attribute_index),
                    )
                    <= 5
                    for cue_index in cue_positions
                ):
                    return True
    return False


def _entity_identifier_attribute_refs(model: StructuredModel, entity_name: str) -> set[str]:
    for entity in model.entities:
        if entity.name == entity_name:
            return {part.ref for part in entity.identifier if part.kind == "attribute"}
    return set()


def _entity_identifier_relationship_refs(model: StructuredModel, entity_name: str) -> set[str]:
    for entity in model.entities:
        if entity.name == entity_name:
            return {part.ref for part in entity.identifier if part.kind == "relationship"}
    return set()


def _relationship_identifier_refs_by_entity(model: StructuredModel) -> dict[str, set[str]]:
    return {
        entity.name: {part.ref for part in entity.identifier if part.kind == "relationship"}
        for entity in model.entities
    }


def _entity_attribute_names(model: StructuredModel) -> dict[str, set[str]]:
    return {
        entity.name: {attribute.name for attribute in entity.attributes}
        for entity in model.entities
    }


def _stated_identifier_removed_by_effect(
    operation: dict[str, Any],
    model: StructuredModel,
    specification: str,
) -> tuple[str, str, str] | None:
    """Return a protected identifier element removed by the operation's full effect.

    Patch normalization can remove an unused fallback ``id`` as a deterministic
    side effect of an otherwise unrelated operation. Simulating against the
    immutable input model also exposes removed relationship identifier parts
    without duplicating patch-engine rules.
    """

    after, result = apply_structured_patch_operation(model, operation)
    if result.get("status") != "accepted":
        return None
    before_attributes = _entity_attribute_names(model)
    after_attributes = _entity_attribute_names(after)
    current_identifier_attributes = {
        entity.name: {part.ref for part in entity.identifier if part.kind == "attribute"}
        for entity in model.entities
    }
    for entity_name, attribute_names in before_attributes.items():
        for attribute_name in sorted(attribute_names - after_attributes.get(entity_name, set())):
            identifier_name_words = _spec_guard_words(attribute_name)
            conventional_identifier_name = any(
                word == "id" or word.startswith("identif")
                for word in identifier_name_words
            )
            if (
                attribute_name not in current_identifier_attributes.get(entity_name, set())
                and not conventional_identifier_name
            ):
                continue
            if specification_appears_to_state_identifier(
                specification,
                entity_name,
                attribute_name,
            ):
                return "attribute", entity_name, attribute_name
    before_relationship_refs = _relationship_identifier_refs_by_entity(model)
    after_relationship_refs = _relationship_identifier_refs_by_entity(after)
    for entity_name, relationship_refs in before_relationship_refs.items():
        for relationship_ref in sorted(
            relationship_refs - after_relationship_refs.get(entity_name, set())
        ):
            if specification_appears_to_state_identifier(
                specification,
                entity_name,
                relationship_ref,
            ):
                return "relationship", entity_name, relationship_ref
    return None


def stated_identifier_patch_guard_reason(
    operation: dict[str, Any],
    model: StructuredModel,
    specification: str,
) -> str | None:
    normalized = normalized_operation_signature_payload(operation)
    if not normalized:
        return None
    op_name = str(normalized.get("op") or "")
    if op_name == "setIdentifier":
        entity_name = str(normalized.get("entity") or "")
        current_attribute_refs = _entity_identifier_attribute_refs(model, entity_name)
        current_relationship_refs = _entity_identifier_relationship_refs(model, entity_name)
        new_attribute_refs = {
            str(part.get("ref") or "")
            for part in (normalized.get("parts") or [])
            if isinstance(part, dict) and part.get("kind") == "attribute"
        }
        new_relationship_refs = {
            str(part.get("ref") or "")
            for part in (normalized.get("parts") or [])
            if isinstance(part, dict) and part.get("kind") == "relationship"
        }
        for removed_ref in sorted(current_attribute_refs - new_attribute_refs):
            if specification_appears_to_state_identifier(specification, entity_name, removed_ref):
                return (
                    f"Rejected identifier rewrite: the specification appears to state '{entity_name}.{removed_ref}' "
                    "as an identifier, so a correction cannot replace it with a merely plausible alternative."
                )
        for removed_ref in sorted(current_relationship_refs - new_relationship_refs):
            if specification_appears_to_state_identifier(specification, entity_name, removed_ref):
                return (
                    "Rejected identifier rewrite: the specification appears to state relationship "
                    f"'{removed_ref}' as part of the identifier for '{entity_name}', so a correction cannot "
                    "replace it with a merely plausible alternative."
                )
    if op_name == "removeAttribute":
        entity_name = str(normalized.get("entity") or "")
        attribute_name = str(normalized.get("name") or "")
        if (
            attribute_name in _entity_identifier_attribute_refs(model, entity_name)
            and specification_appears_to_state_identifier(specification, entity_name, attribute_name)
        ):
            return (
                f"Rejected attribute removal: the specification appears to state '{entity_name}.{attribute_name}' "
                "as an identifier."
            )
    removed_by_effect = _stated_identifier_removed_by_effect(operation, model, specification)
    if removed_by_effect is not None:
        identifier_kind, entity_name, identifier_ref = removed_by_effect
        if identifier_kind == "relationship":
            return (
                "Rejected correction side effect: applying the operation would remove relationship "
                f"'{identifier_ref}' from the identifier for '{entity_name}', which the specification appears "
                "to state as identifying that entity."
            )
        return (
            "Rejected correction side effect: applying the operation and its deterministic repairs would remove "
            f"'{entity_name}.{identifier_ref}', which the specification appears to state as an identifier."
        )
    return None


LEGACY_POSTHOC_CORRECTION_POLICY = CorrectionPhasePolicy(
    policy_id="legacy-posthoc-v1",
    operation_guard=None,
    refined=False,
    success_stop_reason="async_op_patch_model_posthoc_correction_complete",
)

REFINED_CORRECTION_POLICY = CorrectionPhasePolicy(
    policy_id="structured-patch-refined-v2",
    operation_guard=None,
    refined=True,
    success_stop_reason="async_op_patch_model_refined_correction_complete",
    name_policy=UNICODE_NFKC_NAME_POLICY,
)


__all__ = [
    "CorrectionOperationGuard",
    "CorrectionPhasePolicy",
    "LEGACY_POSTHOC_CORRECTION_POLICY",
    "REFINED_CORRECTION_POLICY",
    "specification_appears_to_state_identifier",
    "stated_identifier_patch_guard_reason",
]
