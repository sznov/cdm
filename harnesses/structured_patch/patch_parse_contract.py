from __future__ import annotations

from typing import Any


STRUCTURED_PATCH_OP_ALIASES = {
    "add_entity": "addEntity",
    "addentity": "addEntity",
    "ADD_ENTITY": "addEntity",
    "remove_entity": "removeEntity",
    "removeentity": "removeEntity",
    "REMOVE_ENTITY": "removeEntity",
    "add_attribute": "addAttribute",
    "addattribute": "addAttribute",
    "ADD_ATTRIBUTE": "addAttribute",
    "remove_attribute": "removeAttribute",
    "removeattribute": "removeAttribute",
    "REMOVE_ATTRIBUTE": "removeAttribute",
    "add_relationship": "addRelationship",
    "addrelationship": "addRelationship",
    "ADD_RELATIONSHIP": "addRelationship",
    "remove_relationship": "removeRelationship",
    "removerelationship": "removeRelationship",
    "REMOVE_RELATIONSHIP": "removeRelationship",
    "set_identifier": "setIdentifier",
    "setidentifier": "setIdentifier",
    "SET_IDENTIFIER": "setIdentifier",
    "add_inheritance": "addInheritance",
    "addinheritance": "addInheritance",
    "ADD_INHERITANCE": "addInheritance",
    "remove_inheritance": "removeInheritance",
    "removeinheritance": "removeInheritance",
    "REMOVE_INHERITANCE": "removeInheritance",
    "rename_entity": "renameEntity",
    "renameentity": "renameEntity",
    "RENAME_ENTITY": "renameEntity",
    "rename_attribute": "renameAttribute",
    "renameattribute": "renameAttribute",
    "RENAME_ATTRIBUTE": "renameAttribute",
    "rename_relationship": "renameRelationship",
    "renamerelationship": "renameRelationship",
    "RENAME_RELATIONSHIP": "renameRelationship",
}

STRUCTURED_PATCH_SUPPORTED_OPS = {
    "addEntity",
    "removeEntity",
    "addAttribute",
    "removeAttribute",
    "addRelationship",
    "removeRelationship",
    "setIdentifier",
    "addInheritance",
    "removeInheritance",
    "renameEntity",
    "renameAttribute",
    "renameRelationship",
}

STRUCTURED_PATCH_NOOP_OPS = {"noop", "noOp", "NO_OP", "no_op", "NOOP"}


def canonical_structured_patch_op_name(raw_name: Any) -> str:
    name = str(raw_name or "").strip()
    if not name:
        return ""
    if name in STRUCTURED_PATCH_NOOP_OPS:
        return "noop"
    if name in STRUCTURED_PATCH_SUPPORTED_OPS:
        return name
    return STRUCTURED_PATCH_OP_ALIASES.get(name, STRUCTURED_PATCH_OP_ALIASES.get(name.lower(), name))


def structured_patch_operation_minimal_error(operation: dict[str, Any]) -> str | None:
    op_name = canonical_structured_patch_op_name(operation.get("op") or operation.get("operation") or operation.get("type"))
    if op_name not in STRUCTURED_PATCH_SUPPORTED_OPS:
        return "Unsupported operation."
    if op_name == "addEntity":
        return None if str(operation.get("name") or "").strip() else "addEntity requires name."
    if op_name == "removeEntity":
        return None if str(operation.get("name") or operation.get("entity") or "").strip() else "removeEntity requires name/entity."
    if op_name == "addAttribute":
        if not str(operation.get("entity") or "").strip():
            return "addAttribute requires entity."
        return None if str(operation.get("name") or "").strip() else "addAttribute requires name."
    if op_name == "removeAttribute":
        if not str(operation.get("entity") or "").strip():
            return "removeAttribute requires entity."
        return None if str(operation.get("name") or "").strip() else "removeAttribute requires name."
    if op_name == "addRelationship":
        source = operation.get("source")
        target = operation.get("target")
        if not str(operation.get("name") or "").strip():
            return "addRelationship requires name."
        if not isinstance(source, dict) or not str(source.get("entity") or "").strip():
            return "addRelationship requires source.entity."
        if not isinstance(target, dict) or not str(target.get("entity") or "").strip():
            return "addRelationship requires target.entity."
        return None
    if op_name == "removeRelationship":
        return None if str(operation.get("name") or "").strip() else "removeRelationship requires name."
    if op_name == "setIdentifier":
        if not str(operation.get("entity") or "").strip():
            return "setIdentifier requires entity."
        parts = operation.get("parts")
        if not isinstance(parts, list) or not parts:
            return "setIdentifier requires non-empty parts."
        for part in parts:
            if not isinstance(part, dict) or not str(part.get("kind") or "").strip() or not str(part.get("ref") or "").strip():
                return "setIdentifier parts require kind and ref."
        return None
    if op_name == "addInheritance":
        if not str(operation.get("entity") or "").strip():
            return "addInheritance requires entity."
        return None if str(operation.get("parent") or operation.get("parent_entity") or "").strip() else "addInheritance requires parent."
    if op_name == "removeInheritance":
        if not str(operation.get("entity") or "").strip():
            return "removeInheritance requires entity."
        return None if str(operation.get("parent") or operation.get("parent_entity") or "").strip() else "removeInheritance requires parent."
    if op_name == "renameEntity":
        if not str(operation.get("old") or operation.get("entity") or "").strip():
            return "renameEntity requires old/entity."
        return None if str(operation.get("new") or operation.get("name") or "").strip() else "renameEntity requires new/name."
    if op_name == "renameAttribute":
        if not str(operation.get("entity") or "").strip():
            return "renameAttribute requires entity."
        if not str(operation.get("old") or operation.get("name") or "").strip():
            return "renameAttribute requires old/name."
        return None if str(operation.get("new") or "").strip() else "renameAttribute requires new."
    if op_name == "renameRelationship":
        if not str(operation.get("old") or operation.get("name") or "").strip():
            return "renameRelationship requires old/name."
        return None if str(operation.get("new") or "").strip() else "renameRelationship requires new."
    return None


__all__ = [
    "STRUCTURED_PATCH_OP_ALIASES",
    "STRUCTURED_PATCH_SUPPORTED_OPS",
    "STRUCTURED_PATCH_NOOP_OPS",
    "canonical_structured_patch_op_name",
    "structured_patch_operation_minimal_error",
]
