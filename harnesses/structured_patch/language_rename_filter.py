from __future__ import annotations

from typing import Any

from harnesses.structured_patch.language_association_support import (
    association_entity_can_accept_partially_supported_name,
    supported_association_entity_fallback_name,
)
from harnesses.structured_patch.language_rename_candidates import (
    UNSUPPORTED_SPEC_LANGUAGE_RENAME_REASON,
    normalize_language_rename_candidate,
    rejected_language_rename_payload,
    unsupported_spec_language_rejection,
)
from harnesses.structured_patch.language_word_support import (
    rename_adds_only_short_suffix,
    repair_name_support,
    spec_word_set,
)
from core.schemas import StructuredModel


def filter_structured_language_renames(
    *,
    specification: str,
    model: StructuredModel,
    renames: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    spec_words = spec_word_set(specification)
    entity_names = {entity.name for entity in model.entities}
    relationships = model.relationships
    accepted: list[dict[str, str]] = []
    rejected: list[dict[str, Any]] = []
    entity_rename_map: dict[str, str] = {}
    entity_new_to_old: dict[str, str] = {}
    taken_entity_names = set(entity_names)

    def reject(rename: dict[str, str], reason: str, **extra: Any) -> None:
        rejected.append(rejected_language_rename_payload(rename, reason, **extra))

    def supported_or_reject(rename: dict[str, str]) -> bool:
        rejection = unsupported_spec_language_rejection(rename, spec_words=spec_words)
        if rejection is None:
            return True
        rejected.append(rejection)
        return False

    for rename in renames:
        if (rename.get("kind") or "").strip() != "entity":
            continue
        normalized = normalize_language_rename_candidate(rename, kind="entity")
        old = normalized["old"]
        new = normalized["new"]
        if not old or not new or old == new:
            reject(normalized, "Entity rename rejected because it has no effective old/new name.")
            continue
        if old not in entity_names:
            reject(normalized, "Entity rename rejected because the old entity does not exist.")
            continue
        if rename_adds_only_short_suffix(old, new):
            reject(
                normalized,
                "Entity rename rejected because it only appends a short acronym-like suffix to an existing full name.",
            )
            continue
        if old in entity_rename_map:
            reject(normalized, "Entity rename rejected because this entity already has an accepted rename.")
            continue
        if new in taken_entity_names and new != old:
            reject(normalized, "Entity rename rejected because the new entity name already exists.")
            continue
        support = repair_name_support(new, spec_words=spec_words)
        if not support["supported"]:
            entity = next((item for item in model.entities if item.name == old), None)
            if entity is not None and association_entity_can_accept_partially_supported_name(
                entity=entity,
                model=model,
                proposed_name=new,
                renames=renames,
                spec_words=spec_words,
            ):
                normalized["reason"] = (
                    f"{normalized['reason']} Accepted a partially spec-supported association name because "
                    "the association carries a spec-supported fact."
                ).strip()
                entity_rename_map[old] = new
                entity_new_to_old[new] = old
                taken_entity_names.discard(old)
                taken_entity_names.add(new)
                accepted.append(normalized)
                continue
            fallback = (
                supported_association_entity_fallback_name(
                    entity=entity,
                    model=model,
                    renames=renames,
                    spec_words=spec_words,
                )
                if entity is not None
                else None
            )
            if fallback and fallback != old and fallback not in taken_entity_names:
                normalized["new"] = fallback
                normalized["reason"] = (
                    f"{normalized['reason']} Fallback used a spec-supported association fact name after "
                    "the proposed entity name was not supported by the specification language."
                ).strip()
                new = fallback
            else:
                reject(
                    normalized,
                    UNSUPPORTED_SPEC_LANGUAGE_RENAME_REASON,
                    unsupported_words=support["unsupported_words"],
                )
                continue
        entity_rename_map[old] = new
        entity_new_to_old[new] = old
        taken_entity_names.discard(old)
        taken_entity_names.add(new)
        accepted.append(normalized)

    attribute_names_by_entity = {
        entity.name: {attribute.name for attribute in entity.attributes}
        for entity in model.entities
    }
    taken_attribute_names = {entity_name: set(names) for entity_name, names in attribute_names_by_entity.items()}
    relationship_names = {relationship.name for relationship in relationships if relationship.name}
    taken_relationship_names = set(relationship_names)
    accepted_attribute_keys: set[tuple[str, str]] = set()
    accepted_relationship_old_names: set[str] = set()

    for rename in renames:
        kind = (rename.get("kind") or "").strip()
        if kind == "entity":
            continue
        if kind not in {"attribute", "relationship"}:
            reject(rename, "Rename rejected because kind is not entity, attribute, or relationship.")
            continue
        normalized = normalize_language_rename_candidate(rename, kind=kind)
        old = normalized["old"]
        new = normalized["new"]
        if not old or not new or old == new:
            reject(normalized, "Rename rejected because it has no effective old/new name.")
            continue
        if not supported_or_reject(normalized):
            continue

        if kind == "attribute":
            raw_entity = normalized["entity"]
            entity_name = raw_entity
            if entity_name not in entity_names and entity_name in entity_new_to_old:
                entity_name = entity_new_to_old[entity_name]
            if entity_name not in entity_names:
                reject(normalized, "Attribute rename rejected because the referenced entity does not exist.")
                continue
            attr_names = attribute_names_by_entity.get(entity_name, set())
            if old not in attr_names:
                reject(normalized, "Attribute rename rejected because the old attribute does not exist on the entity.")
                continue
            if (entity_name, old) in accepted_attribute_keys:
                reject(normalized, "Attribute rename rejected because this attribute already has an accepted rename.")
                continue
            if old.lower() == "id" and new.lower() != "id":
                reject(normalized, "Attribute rename rejected because a surrogate id must not be language-repaired into a domain attribute.")
                continue
            if new in taken_attribute_names[entity_name] and new != old:
                reject(normalized, "Attribute rename rejected because the new attribute name already exists on the entity.")
                continue
            normalized["entity"] = entity_name
            accepted_attribute_keys.add((entity_name, old))
            taken_attribute_names[entity_name].discard(old)
            taken_attribute_names[entity_name].add(new)
            accepted.append(normalized)
        else:
            if old not in relationship_names:
                reject(normalized, "Relationship rename rejected because the old relationship does not exist.")
                continue
            if old in accepted_relationship_old_names:
                reject(normalized, "Relationship rename rejected because this relationship already has an accepted rename.")
                continue
            if new in taken_relationship_names and new != old:
                reject(normalized, "Relationship rename rejected because the new relationship name already exists.")
                continue
            accepted_relationship_old_names.add(old)
            taken_relationship_names.discard(old)
            taken_relationship_names.add(new)
            accepted.append(normalized)

    return accepted, rejected


__all__ = ["filter_structured_language_renames"]
