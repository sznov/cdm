from __future__ import annotations

from harnesses.structured_patch.language_association_support import (
    association_entity_can_accept_partially_supported_name,
    entity_supported_fact_names,
    relationship_count_for_entity,
    supported_association_entity_fallback_name,
)
from harnesses.structured_patch.language_word_support import (
    repair_name_support,
    repair_word_supported_by_spec,
    rename_adds_only_short_suffix,
    spec_word_set,
    string_distance_at_most_one,
    structured_concept_key,
    supported_words_in_name,
)

__all__ = [
    "structured_concept_key",
    "string_distance_at_most_one",
    "spec_word_set",
    "repair_word_supported_by_spec",
    "repair_name_support",
    "rename_adds_only_short_suffix",
    "relationship_count_for_entity",
    "entity_supported_fact_names",
    "supported_words_in_name",
    "association_entity_can_accept_partially_supported_name",
    "supported_association_entity_fallback_name",
]
