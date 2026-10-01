from __future__ import annotations

from typing import Any

from harnesses.structured_patch.coverage_name_similarity import compare_name_similarity


def exact_overlap_summary(actual_items: set[Any], reference_items: set[Any]) -> dict[str, Any]:
    matched = actual_items & reference_items
    missing = reference_items - actual_items
    extra = actual_items - reference_items
    precision = len(matched) / len(actual_items) if actual_items else 0.0
    recall = len(matched) / len(reference_items) if reference_items else 0.0
    return {
        "actual_count": len(actual_items),
        "reference_count": len(reference_items),
        "matched_count": len(matched),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "matched": sorted(matched),
        "missing_sample": sorted(missing)[:20],
        "extra_sample": sorted(extra)[:20],
    }


def soft_entity_overlap_summary(
    actual_entities: set[str],
    reference_entities: set[str],
    *,
    threshold: float = 0.62,
) -> tuple[dict[str, Any], dict[str, str]]:
    candidates: list[tuple[float, str, str]] = []
    for actual_name in actual_entities:
        for reference_name in reference_entities:
            score = compare_name_similarity(actual_name, reference_name)
            if score >= threshold:
                candidates.append((score, actual_name, reference_name))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))

    matched_actual: set[str] = set()
    matched_reference: set[str] = set()
    matches: list[dict[str, Any]] = []
    name_map: dict[str, str] = {}
    for score, actual_name, reference_name in candidates:
        if actual_name in matched_actual or reference_name in matched_reference:
            continue
        matched_actual.add(actual_name)
        matched_reference.add(reference_name)
        name_map[actual_name] = reference_name
        matches.append(
            {
                "actual": actual_name,
                "reference": reference_name,
                "score": round(score, 4),
            }
        )

    precision = len(matches) / len(actual_entities) if actual_entities else 0.0
    recall = len(matches) / len(reference_entities) if reference_entities else 0.0
    return (
        {
            "actual_count": len(actual_entities),
            "reference_count": len(reference_entities),
            "matched_count": len(matches),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "matches": matches[:40],
            "missing_sample": sorted(reference_entities - matched_reference)[:20],
            "extra_sample": sorted(actual_entities - matched_actual)[:20],
        },
        name_map,
    )


def soft_relationship_endpoint_overlap_summary(
    actual_pairs: set[tuple[str | None, str | None]],
    reference_pairs: set[tuple[str | None, str | None]],
    entity_name_map: dict[str, str],
) -> dict[str, Any]:
    def canonical_pair(pair: tuple[str | None, str | None]) -> tuple[str, str] | None:
        left, right = pair
        if not left or not right:
            return None
        mapped_left = entity_name_map.get(left)
        mapped_right = entity_name_map.get(right)
        if not mapped_left or not mapped_right:
            return None
        return tuple(sorted((mapped_left, mapped_right)))

    actual_canonical = {pair for pair in (canonical_pair(item) for item in actual_pairs) if pair}
    reference_canonical = {
        tuple(sorted((left, right)))
        for left, right in reference_pairs
        if left and right
    }
    matched = actual_canonical & reference_canonical
    precision = len(matched) / len(actual_pairs) if actual_pairs else 0.0
    recall = len(matched) / len(reference_canonical) if reference_canonical else 0.0
    return {
        "actual_count": len(actual_pairs),
        "reference_count": len(reference_canonical),
        "mappable_actual_count": len(actual_canonical),
        "matched_count": len(matched),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "matched": sorted(matched),
        "missing_sample": sorted(reference_canonical - matched)[:20],
        "extra_sample": sorted(actual_canonical - matched)[:20],
    }


__all__ = [
    "exact_overlap_summary",
    "soft_entity_overlap_summary",
    "soft_relationship_endpoint_overlap_summary",
]
