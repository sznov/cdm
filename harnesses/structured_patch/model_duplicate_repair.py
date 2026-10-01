from __future__ import annotations

from harnesses.structured_patch.model_duplicate_entities import (
    coerce_attribute_list,
    repair_structured_duplicate_entities_payload,
)
from harnesses.structured_patch.model_duplicate_relationships import (
    repair_structured_duplicate_relationship_names_payload,
)

__all__ = [
    "coerce_attribute_list",
    "repair_structured_duplicate_entities_payload",
    "repair_structured_duplicate_relationship_names_payload",
]
