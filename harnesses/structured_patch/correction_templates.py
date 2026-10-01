from __future__ import annotations

from typing import Any

DEFAULT_CORRECTION_TEMPLATE_ID = "default-correction-sequence"
SINGLE_CONSERVATIVE_CORRECTION_TEMPLATE_ID = "single-conservative-correction-pass"
SINGLE_CONSERVATIVE_CORRECTION_MESSAGE = (
    "Run one conservative post-hoc correction pass. Check for the same issue families as the multi-step correction "
    "sequence: semantic errors; temporal/historical association issues; lookup-string issues; wrong multiplicities; "
    "spec-derived natural identifier opportunities; and general identifier issues. Correct only clear, spec-grounded "
    "problems, and prefer small additive repairs over destructive rewrites. Prioritize missing high-impact persistent "
    "concepts, relationships, inheritance, attributes, lookup/reference concepts, generated/stored documents or "
    "evidence, contextual identifiers, and repeated/process-child discriminators. For temporal or historical "
    "associations, reify only when the specification implies repeated occurrences, history, status lifecycle, period, "
    "role, assignment, registration, appointment, employer, amount, signature, date, or stored evidence. For lookup "
    "strings, extract only clear persistent controlled concepts and preserve all code, required-count, limit, "
    "threshold, discriminator, order, line-item, ownership/right, or rule semantics carried by the original scalar. "
    "Do not extract weak status/type/category lookups merely because a scalar is named like a status or type; extract "
    "only when the specification treats the values as a persistent controlled concept, lifecycle state, rule-bearing "
    "category, or independently managed reference data. "
    "If a scalar/category helped identify, classify, order, or distinguish instances, add the replacement relationship, "
    "update affected identifiers, and remove the redundant scalar only when the replacement preserves the same fact in "
    "the same correction; otherwise leave the scalar in place. If the scalar helped identify or distinguish the owner "
    "entity, update the owner identifier or equivalent constraint to use the replacement relationship before removing "
    "the scalar. Remove an existing attribute or relationship only when it is unsupported by the specification, "
    "redundant after a fact-preserving replacement, or superseded by an equivalent corrected artifact emitted in the "
    "same correction. For multiplicities, "
    "change endpoint cardinality only when the current cardinality clearly contradicts explicit specification "
    "evidence; if both current and proposed cardinalities are defensible, emit no operation for that issue. For "
    "identifiers, preserve identifiers explicitly stated by the specification, replace surrogate IDs only when a "
    "complete spec-derived natural/contextual identifier already exists or can be safely added in the same correction, "
    "and keep surrogate IDs when no complete semantic identifier is available. If several role entities repeat shared "
    "person/contact facts, add a shared supertype and inheritance when supported. Move or remove subtype attributes "
    "only if every removed fact remains represented on the supertype or by an equivalent relationship; do not create a "
    "partial supertype that preserves only some shared facts while making other person/contact facts harder to "
    "represent. Do not rename or flatten existing artifacts in this conservative pass; leave naming cleanup for a "
    "later review."
)

CORRECTION_TEMPLATE_REVISIONS = {
    DEFAULT_CORRECTION_TEMPLATE_ID: "default-correction-sequence-v1",
    SINGLE_CONSERVATIVE_CORRECTION_TEMPLATE_ID: "single-conservative-correction-pass-v1",
}

CORRECTION_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": DEFAULT_CORRECTION_TEMPLATE_ID,
        "name": "Default Correction Sequence",
        "description": "Runs the broad post-modeling correction passes that have been useful in manual review.",
        "steps": [
            {
                "id": "semantic-errors",
                "name": "Semantic Errors",
                "message": (
                    "Check for semantic errors and correct them if any are found. Preserve existing modeled facts "
                    "unless the specification clearly makes them unsupported or the replacement preserves the same fact."
                ),
            },
            {
                "id": "temporal-historical-associations",
                "name": "Temporal Historical Associations",
                "message": (
                    "Check for temporal or historical association issues and correct them if any are found. Reify only "
                    "when the specification implies repeated occurrences, history, status lifecycle, period, role, "
                    "assignment, registration, appointment, or stored evidence. Do not invent date, status, order-number, "
                    "audit, or validation facts without specification support."
                ),
            },
            {
                "id": "lookup-strings",
                "name": "Lookup Strings",
                "message": (
                    "Check for lookup-string issues and correct them if any are found. Extract only clear persistent "
                    "controlled concepts, and preserve all code, required-count, limit, threshold, discriminator, "
                    "order, line-item, ownership/right, or rule semantics carried by the original scalar/category. "
                    "If the removed scalar/category helped identify or distinguish instances, add the replacement "
                    "relationship and update affected identifiers in the same correction; otherwise leave the scalar "
                    "in place. Do not push shared supertype facts down into subtypes."
                ),
            },
            {
                "id": "wrong-multiplicities",
                "name": "Wrong Multiplicities",
                "message": (
                    "Check for relationship multiplicity issues and correct them if any are found. Only change "
                    "multiplicity when the current endpoint cardinality clearly contradicts explicit specification "
                    'evidence. If both current and proposed cardinalities are defensible, emit {"op":"noop"}.'
                ),
                "allowed_ops": ["addRelationship"],
            },
            {
                "id": "spec-derived-natural-identifiers",
                "name": "Spec-Derived Natural Identifiers",
                "message": (
                    "Check for cases where surrogate ID is used that is not prescribed by the spec, "
                    "but there is a COMPLETE spec-derived natural identifier (which could consist of "
                    "attributes and identifying relationships). If a spec-derived natural ID cannot "
                    "satisfy semantic constraints, then use a surrogate ID. Do not remove a surrogate "
                    "identifier unless every required identifying attribute or relationship already exists "
                    "or can be safely added in the same correction. Preserve identifiers explicitly stated by "
                    "the specification; do not replace an existing stated identifier merely because another "
                    "natural or contextual identifier is plausible."
                ),
                "allowed_ops": ["setIdentifier", "removeAttribute"],
            },
            {
                "id": "identifier-issues",
                "name": "Identifier Issues",
                "message": (
                    "Check for identifier issues and correct them if any are found. Keep stated identifiers, "
                    "preserve shared supertype identifiers and names, and do not move a common identifier/name "
                    "only into subtypes while the meaningful supertype remains modeled. Do not replace an explicit "
                    "identifier with a plausible alternative unless the specification itself says the existing "
                    "identifier is insufficient or wrong."
                ),
                "allowed_ops": ["setIdentifier", "addAttribute", "removeAttribute"],
            },
        ],
    },
    {
        "id": SINGLE_CONSERVATIVE_CORRECTION_TEMPLATE_ID,
        "name": "Single Conservative Correction Pass",
        "description": "Runs one fact-preserving post-hoc repair prompt that combines the default correction concerns.",
        "steps": [
            {
                "id": "single-conservative-correction-pass",
                "name": "Single Conservative Correction Pass",
                "message": SINGLE_CONSERVATIVE_CORRECTION_MESSAGE,
                "allowed_ops": [
                    "addEntity",
                    "addAttribute",
                    "removeAttribute",
                    "addRelationship",
                    "removeRelationship",
                    "addInheritance",
                    "setIdentifier",
                ],
            }
        ],
    },
]


def correction_template_by_id(template_id: str) -> dict[str, Any] | None:
    for template in CORRECTION_TEMPLATES:
        if template.get("id") == template_id:
            return template
    return None


__all__ = [
    "CORRECTION_TEMPLATES",
    "CORRECTION_TEMPLATE_REVISIONS",
    "DEFAULT_CORRECTION_TEMPLATE_ID",
    "SINGLE_CONSERVATIVE_CORRECTION_MESSAGE",
    "SINGLE_CONSERVATIVE_CORRECTION_TEMPLATE_ID",
    "correction_template_by_id",
]
