from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.model_duplicate_entities import repair_structured_duplicate_entities_payload
from harnesses.structured_patch.model_duplicate_relationships import (
    repair_structured_duplicate_relationship_names_payload,
)
from harnesses.structured_patch.model_name_repair import repair_structured_model_names_payload
from harnesses.structured_patch.model_typed_attribute_repair import repair_structured_entity_typed_attributes_payload
from harnesses.structured_patch.model_typed_attribute_targets import (
    entity_target_for_attribute_name,
    entity_target_for_attribute_type,
    relationship_base_name_for_entity_attribute,
    relationship_name_for_typed_attribute,
)
from harnesses.structured_patch.model_payload_endpoints import add_missing_endpoint_entities
from harnesses.structured_patch.model_payload_identifiers import repair_structured_model_identifier_payloads
from harnesses.structured_patch.model_payload_shape import sanitize_structured_model_payload_shape
from harnesses.structured_patch.patch_normalization import (
    repair_relationship_identified_association_multiplicities_payload,
)

















def repair_structured_model_payload(
    payload: Any,
    *,
    repair_missing_endpoint_entities: bool = False,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> Any:
    if not isinstance(payload, dict) or not isinstance(payload.get("entities"), list):
        return payload
    repaired = repair_structured_model_names_payload(payload, name_policy=name_policy)
    repaired = repair_structured_entity_typed_attributes_payload(
        repaired,
        name_policy=name_policy,
    )
    repaired = repair_structured_duplicate_entities_payload(repaired, name_policy=name_policy)
    repaired = repair_structured_duplicate_relationship_names_payload(
        repaired,
        name_policy=name_policy,
    )
    repaired = sanitize_structured_model_payload_shape(repaired)

    if repair_missing_endpoint_entities:
        repaired = add_missing_endpoint_entities(repaired, name_policy=name_policy)

    repaired = repair_structured_model_identifier_payloads(
        repaired,
        name_policy=name_policy,
    )
    repair_relationship_identified_association_multiplicities_payload(repaired)
    return repaired

__all__ = [
    "entity_target_for_attribute_name",
    "entity_target_for_attribute_type",
    "relationship_base_name_for_entity_attribute",
    "relationship_name_for_typed_attribute",
    "repair_structured_duplicate_entities_payload",
    "repair_structured_duplicate_relationship_names_payload",
    "repair_structured_entity_typed_attributes_payload",
    "repair_structured_model_names_payload",
    "repair_structured_model_payload",
]
