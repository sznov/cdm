from __future__ import annotations

from harnesses.structured_patch.patch_model_lookup import (
    find_structured_entity_payload,
    resolve_structured_entity_name,
    structured_entity_attribute_names,
    structured_entity_name_from_ref,
    structured_entity_names,
    structured_model_from_payload,
)
from harnesses.structured_patch.patch_payload_normalization import (
    add_missing_surrogate_id_identifier_attributes,
    normalize_structured_attributes_payload,
    normalize_structured_identifier_parts,
    normalize_structured_relationship_end_payload,
    normalize_structured_relationship_payload,
    structured_relationship_matches,
)
from harnesses.structured_patch.patch_payload_repair import (
    remove_unused_fallback_id_attributes,
    repair_relationship_identified_association_multiplicities_payload,
    validate_structured_patch_payload,
)
from harnesses.structured_patch.patch_scalar_normalization import (
    STRUCTURED_ATTRIBUTE_TYPE_ALIASES,
    STRUCTURED_ATTRIBUTE_TYPES,
    normalize_structured_attribute_type,
    normalize_structured_multiplicity,
    normalize_structured_name,
)

__all__ = [
    "STRUCTURED_ATTRIBUTE_TYPES",
    "STRUCTURED_ATTRIBUTE_TYPE_ALIASES",
    "normalize_structured_name",
    "normalize_structured_multiplicity",
    "normalize_structured_attribute_type",
    "structured_model_from_payload",
    "structured_entity_names",
    "resolve_structured_entity_name",
    "structured_entity_name_from_ref",
    "find_structured_entity_payload",
    "structured_entity_attribute_names",
    "add_missing_surrogate_id_identifier_attributes",
    "normalize_structured_attributes_payload",
    "normalize_structured_identifier_parts",
    "normalize_structured_relationship_end_payload",
    "normalize_structured_relationship_payload",
    "structured_relationship_matches",
    "validate_structured_patch_payload",
    "remove_unused_fallback_id_attributes",
    "repair_relationship_identified_association_multiplicities_payload",
]
