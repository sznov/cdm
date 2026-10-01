from __future__ import annotations

from copy import deepcopy
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
    StructuredNamePolicyError,
)
from harnesses.structured_patch.patch_normalization import normalize_structured_name


def repair_structured_duplicate_relationship_names_payload(
    payload: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> dict[str, Any]:
    repaired = deepcopy(payload)
    relationships = repaired.get("relationships")
    entities = repaired.get("entities")
    if not isinstance(relationships, list) or not isinstance(entities, list):
        return repaired

    grouped_relationships: dict[str, list[tuple[int, dict[str, Any], set[str]]]] = {}
    canonical_names: dict[str, str] = {}
    for index, relationship in enumerate(relationships):
        if not isinstance(relationship, dict):
            continue
        name = str(relationship.get("name") or "").strip()
        if not name:
            continue
        endpoints: set[str] = set()
        for end_key in ("source", "target"):
            end = relationship.get(end_key)
            if isinstance(end, dict) and str(end.get("entity") or "").strip():
                endpoints.add(str(end.get("entity") or "").strip())
        name_key = name_policy.comparison_key(name)
        existing_name = canonical_names.get(name_key)
        if existing_name is not None and existing_name != name:
            raise StructuredNamePolicyError(
                f"Relationship names {existing_name!r} and {name!r} collide after NFKC case-folding."
            )
        canonical_names[name_key] = name
        grouped_relationships.setdefault(name_key, []).append((index, relationship, endpoints))

    duplicate_groups = {
        name_key: group
        for name_key, group in grouped_relationships.items()
        if len(group) > 1
    }
    if not duplicate_groups:
        return repaired

    used_names = {
        name_policy.comparison_key(str(relationship.get("name") or "").strip())
        for relationship in relationships
        if isinstance(relationship, dict) and str(relationship.get("name") or "").strip()
    }
    for name_key in duplicate_groups:
        used_names.discard(name_key)

    renamed_groups: dict[str, list[tuple[str, set[str]]]] = {}
    for name_key, group in duplicate_groups.items():
        name = canonical_names[name_key]
        renamed_groups[name_key] = []
        for ordinal, (_index, relationship, endpoints) in enumerate(group, start=1):
            source = ""
            target = ""
            if isinstance(relationship.get("source"), dict):
                source = str(relationship["source"].get("entity") or "").strip()
            if isinstance(relationship.get("target"), dict):
                target = str(relationship["target"].get("entity") or "").strip()
            base_candidate = normalize_structured_name(
                f"{name} {source} {target}",
                style="lower",
                name_policy=name_policy,
            )
            if (
                not isinstance(base_candidate, str)
                or not base_candidate.strip()
                or name_policy.names_equal(base_candidate, name)
            ):
                base_candidate = f"{name}{ordinal}"
            candidate = base_candidate
            counter = 2
            while name_policy.comparison_key(candidate) in used_names:
                candidate = f"{base_candidate}{counter}"
                counter += 1
            relationship["name"] = candidate
            used_names.add(name_policy.comparison_key(candidate))
            renamed_groups[name_key].append((candidate, endpoints))

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_name = str(entity.get("name") or "").strip()
        identifier = entity.get("identifier")
        if not isinstance(identifier, list):
            continue
        repaired_identifier: list[Any] = []
        seen_parts: set[tuple[str, str]] = set()
        for part in identifier:
            if not isinstance(part, dict) or part.get("kind") != "relationship":
                repaired_identifier.append(part)
                if isinstance(part, dict):
                    seen_parts.add((str(part.get("kind") or ""), str(part.get("ref") or "")))
                continue
            ref = str(part.get("ref") or "").strip()
            renamed_candidates = [
                new_name
                for new_name, endpoints in renamed_groups.get(name_policy.comparison_key(ref), [])
                if entity_name
                and any(name_policy.names_equal(entity_name, endpoint) for endpoint in endpoints)
            ]
            if not renamed_candidates:
                repaired_identifier.append(part)
                seen_parts.add(("relationship", ref))
                continue
            for new_name in renamed_candidates:
                key = ("relationship", new_name)
                if key in seen_parts:
                    continue
                repaired_identifier.append({"kind": "relationship", "ref": new_name})
                seen_parts.add(key)
        entity["identifier"] = repaired_identifier

    return repaired


__all__ = ["repair_structured_duplicate_relationship_names_payload"]
