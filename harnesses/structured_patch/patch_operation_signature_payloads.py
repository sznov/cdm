from __future__ import annotations

from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_parse_contract import (
    STRUCTURED_PATCH_SUPPORTED_OPS,
    canonical_structured_patch_op_name,
)
from harnesses.structured_patch.patch_normalization import (
    normalize_structured_attribute_type,
    normalize_structured_attributes_payload,
    normalize_structured_identifier_parts,
    normalize_structured_name,
    normalize_structured_relationship_end_payload,
    normalize_structured_relationship_payload,
)
from core.schemas import StructuredOutputError


def normalized_operation_signature_payload(
    operation: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any] | None:
    if not isinstance(operation, dict):
        return None
    op = dict(operation)
    op_name = canonical_structured_patch_op_name(op.get("op") or op.get("operation") or op.get("type"))
    if op_name not in STRUCTURED_PATCH_SUPPORTED_OPS:
        return {"op": op_name or ""}
    try:
        if op_name == "addEntity":
            return {
                "op": op_name,
                "name": normalize_structured_name(
                    op.get("name") or op.get("entity"),
                    style="upper",
                    name_policy=name_policy,
                ),
                "attributes": normalize_structured_attributes_payload(
                    op.get("attributes"),
                    name_policy=name_policy,
                ),
                "identifier": sorted(
                    normalize_structured_identifier_parts(
                        op.get("identifier") or op.get("parts"),
                        name_policy=name_policy,
                    ),
                    key=lambda part: (
                        part["kind"],
                        name_policy.comparison_key(part["ref"]),
                    ),
                ),
                "inherits_from": sorted(
                    (
                        str(
                            normalize_structured_name(
                                parent,
                                style="upper",
                                name_policy=name_policy,
                            )
                            or ""
                        )
                        for parent in (op.get("inherits_from") or op.get("inheritsFrom") or [])
                        if str(parent or "").strip()
                    ),
                    key=name_policy.comparison_key,
                ),
            }
        if op_name == "removeEntity":
            return {
                "op": op_name,
                "name": normalize_structured_name(
                    op.get("name") or op.get("entity"),
                    style="upper",
                    name_policy=name_policy,
                ),
            }
        if op_name == "addAttribute":
            return {
                "op": op_name,
                "entity": normalize_structured_name(
                    op.get("entity") or op.get("entityName"),
                    style="upper",
                    name_policy=name_policy,
                ),
                "name": normalize_structured_name(
                    op.get("name") or op.get("attribute"),
                    style="lower",
                    name_policy=name_policy,
                ),
                "type": normalize_structured_attribute_type(op.get("type")),
            }
        if op_name == "removeAttribute":
            return {
                "op": op_name,
                "entity": normalize_structured_name(
                    op.get("entity") or op.get("entityName"),
                    style="upper",
                    name_policy=name_policy,
                ),
                "name": normalize_structured_name(
                    op.get("name") or op.get("attribute"),
                    style="lower",
                    name_policy=name_policy,
                ),
            }
        if op_name == "addRelationship":
            relationship = normalize_structured_relationship_payload(op, name_policy=name_policy)
            return {
                "op": op_name,
                "name": relationship.get("name"),
                "source": {
                    "entity": relationship["source"].get("entity"),
                    "multiplicity": relationship["source"].get("multiplicity"),
                    "role": relationship["source"].get("role"),
                },
                "target": {
                    "entity": relationship["target"].get("entity"),
                    "multiplicity": relationship["target"].get("multiplicity"),
                    "role": relationship["target"].get("role"),
                },
            }
        if op_name == "removeRelationship":
            return {
                "op": op_name,
                "name": normalize_structured_name(
                    op.get("name") or op.get("relationship"),
                    style="lower",
                    name_policy=name_policy,
                ),
                "source": normalize_structured_relationship_end_payload(
                    op.get("source"),
                    name_policy=name_policy,
                ).get("entity")
                if op.get("source")
                else None,
                "target": normalize_structured_relationship_end_payload(
                    op.get("target"),
                    name_policy=name_policy,
                ).get("entity")
                if op.get("target")
                else None,
            }
        if op_name == "setIdentifier":
            return {
                "op": op_name,
                "entity": normalize_structured_name(
                    op.get("entity") or op.get("entityName"),
                    style="upper",
                    name_policy=name_policy,
                ),
                "parts": sorted(
                    normalize_structured_identifier_parts(
                        op.get("parts") or op.get("identifier"),
                        name_policy=name_policy,
                    ),
                    key=lambda part: (
                        part["kind"],
                        name_policy.comparison_key(part["ref"]),
                    ),
                ),
            }
        if op_name in {"addInheritance", "removeInheritance"}:
            return {
                "op": op_name,
                "entity": normalize_structured_name(
                    op.get("entity") or op.get("entityName"),
                    style="upper",
                    name_policy=name_policy,
                ),
                "parent": normalize_structured_name(
                    op.get("parent") or op.get("parent_entity"),
                    style="upper",
                    name_policy=name_policy,
                ),
            }
        if op_name == "renameEntity":
            return {
                "op": op_name,
                "old": normalize_structured_name(
                    op.get("old") or op.get("entity"),
                    style="upper",
                    name_policy=name_policy,
                ),
                "new": normalize_structured_name(
                    op.get("new") or op.get("name"),
                    style="upper",
                    name_policy=name_policy,
                ),
            }
        if op_name == "renameAttribute":
            return {
                "op": op_name,
                "entity": normalize_structured_name(
                    op.get("entity"),
                    style="upper",
                    name_policy=name_policy,
                ),
                "old": normalize_structured_name(
                    op.get("old") or op.get("name"),
                    style="lower",
                    name_policy=name_policy,
                ),
                "new": normalize_structured_name(
                    op.get("new"),
                    style="lower",
                    name_policy=name_policy,
                ),
            }
        if op_name == "renameRelationship":
            return {
                "op": op_name,
                "old": normalize_structured_name(
                    op.get("old") or op.get("name"),
                    style="lower",
                    name_policy=name_policy,
                ),
                "new": normalize_structured_name(
                    op.get("new"),
                    style="lower",
                    name_policy=name_policy,
                ),
                "source": normalize_structured_name(
                    op.get("source"),
                    style="upper",
                    name_policy=name_policy,
                )
                if op.get("source")
                else None,
                "target": normalize_structured_name(
                    op.get("target"),
                    style="upper",
                    name_policy=name_policy,
                )
                if op.get("target")
                else None,
            }
    except (TypeError, ValueError, StructuredOutputError):
        pass
    return {"op": op_name, "raw": op}


__all__ = ["normalized_operation_signature_payload"]
