from __future__ import annotations

PATCH_OPERATION_CLERK_SYSTEM_PROMPT = """\
You emit small conceptual-model patch operations.

Convert critic findings or check/correction requests into deterministic operations for the current JSON IR.
Return only JSONL: one JSON object per line. If no operations are needed, return exactly {"op":"noop"}.
Do not include Markdown, comments, analysis, or extra text.
"""

PATCH_OPERATION_CLERK_USER_TEMPLATE = """\
Task:
Patch CURRENT_MODEL by emitting small operation objects. Do not return the full model.

Operation rules:
- Emit one JSON object per line.
- First judge CURRENT_MODEL against the specification using the correction checklist below. If no issues are found, emit exactly {"op":"noop"}.
- If a major process area or subdomain from the specification is still missing, prioritize missing-concept and missing-relationship coverage before identifier, lookup, or temporal polish.
- Use entity names from CURRENT_MODEL when modifying existing artifacts.
- Target existing artifacts by their StructuredModel name fields; do not invent or rely on internal generated E/R ids.
- If a relationship needs an entity that is missing, emit addEntity first, then addRelationship later.
- Keep each operation small and idempotent.
- Do not emit both addRelationship and removeRelationship for the same relationship name/endpoints in one batch.
- To change relationship multiplicity or endpoint role, emit addRelationship with the desired endpoint metadata; the deterministic applier updates an existing same-name/same-endpoint relationship.
- Relationship multiplicity convention: multiplicity belongs to the endpoint entity where it appears and is rendered beside that endpoint. It means how many instances of that endpoint entity may be associated with one instance of the opposite endpoint.
- Example: source ParentEntity multiplicity 0..*, target ChildEntity multiplicity 1 means one ChildEntity can have 0..* ParentEntity instances, and one ParentEntity instance has 1 ChildEntity.
- Do not reinterpret source.multiplicity as the number of target instances per source, do not reinterpret target.multiplicity as the number of source instances per target, and do not flip multiplicities globally.
- Change multiplicities only when specification evidence clearly contradicts the existing endpoint cardinality.
- If both existing and proposed cardinalities are defensible for the current entity interpretation, emit no operation.
- Do not remove an existing relationship unless the finding or user request explicitly says it is wrong, redundant, or replaced by an equivalent relationship.
- Do not remove or replace an existing artifact unless the emitted operations preserve the fact it represented or the specification clearly makes it unsupported.
- Use removeEntity only when an entity is explicitly obsolete after a merge/replacement; remove or replace its relationships first.
- Use names in the specification language, normalized to pure ASCII.
- Entity names use UpperCamelCase; attribute and relationship names use lowerCamelCase.
- Attribute type must be one of: string, int, real, bool, date.
- Prefer natural identifiers stated or clearly implied by the specification over surrogate ids.
- Use {"name":"id","type":"int"} only as a fallback identifier for regular concrete entities with no stated or clearly implied natural identifier.
- Never replace or remove an identifier explicitly stated by the specification merely because a different natural/contextual identifier is plausible.
- Subclasses inherit parent identity by default, but may define their own identifier when the specification gives a subtype-specific natural identifier or contextual/weak identifying structure.
- If a parent is only an abstract classification, it may have no identifier.
- When the same participation could be modeled as several role-specific links or as one association entity, use one association entity with role/type and any period/date facts; do not also keep parallel role-specific links for the same fact.
- Prefer maximal spec-grounded data normalization over flattened attributes.
- Treat grouped multi-field noun phrases as candidate entities, especially when they include date, period, status, registration, role, address/location, or can occur multiple times over time.
- Do not invent date, order-number, status, audit, file-path, validation, count, limit, or threshold facts merely because they are useful in a real system; add them only when the specification states or implies stored evidence, tracking, generated files, ordered document/list items, lifecycle, codes, required counts, limits, or thresholds.
- Extract lookup/reference entities for bounded categories, roles, types, statuses, methods, levels, options, classifications, institutions, and other controlled concepts mentioned by the specification.
- If you extract a scalar/type/status into a lookup/reference entity, preserve all meaningful semantics from the source text such as code, required count, limit, threshold, discriminator, order, ownership/right, or rule facts.
- If removing a scalar/category replaces an identifier, discriminator, order, line-item, ownership/right, status, or type fact, add the replacement relationship and update affected identifiers in the same batch; otherwise do not remove the scalar/category.
- When merging or generalizing repeated item/document/event/line entities, preserve discriminator, order/line-number, quantity, price/amount, status, and contextual identifier facts from the original representation.
- Replace string/scalar attributes with relationships when the value refers to another modeled entity, lookup/reference entity, reusable value object, or clear domain concept.
- Avoid storing the same fact both as a scalar attribute and as a relationship/path; once extracted, keep the normalized relationship representation.
- Keep a scalar attribute flat only when it is intrinsic to exactly one entity and has no identity, lifecycle, history, relationship, reuse, or controlled-vocabulary semantics.
- If a meaningful supertype remains modeled, keep shared names, identifiers, and common properties on the supertype instead of duplicating them only on subtypes.
- Pending decisions below are unresolved user choices. Do not emit an operation that applies, satisfies, or conflicts with a pending decision.
- If a critic finding overlaps a pending decision but is not the same operation, do not apply it automatically; leave it for the decision system.
Correction checklist:
- Check for semantic errors and correct them if any are found.
- Check for one entity conflating several domain concepts; split only when the specification supports the split.
- Check for associations that carry facts such as role, period, appointment, registration, status, employer, amount, signature, or date; model those associations as entities when needed.
- Check for repeated attributes across entities that represent the same fact or concept; normalize them when the shared concept is spec-grounded.
- Check for lookup entity candidates represented as string/scalar attributes; extract clear, persistent controlled concepts.
- When extracting lookups, preserve code, required-count, limit, threshold, discriminator, order, line-item, ownership/right, or rule semantics carried by the original scalar/category.
- Check that lookup extraction updates identifiers or equivalent constraints whenever the removed scalar/category helped identify, order, classify, or distinguish instances.
- Check for string/scalar attributes that actually refer to another modeled entity, clear domain concept, reusable value object, or extractable lookup/reference concept.
- Check grouped value attributes such as address/location/residence/contact blocks; extract them when they have multiple fields, own facts, reuse, history, or relationships.
- Check for missing important relationships and relationship multiplicities that contradict the specification.
- Check identifiers: keep stated identifiers, prefer complete spec-derived natural/contextual identifiers, and use surrogate id only when no complete spec-derived identifier satisfies the semantics.
- Check identifiers without replacing a spec-stated identifier merely because another natural/contextual identifier is plausible.
- Check that identifier rewrites are complete before removing surrogate ids; if a required identifying relationship is missing and cannot be added safely in this batch, leave the identifier unchanged.
- Check that shared supertype facts stay on meaningful supertypes instead of being duplicated only on subtypes.
- Check for duplicated information across attributes, relationships, or parallel paths; prefer the normalized representation.
- Do not emit speculative corrections. If evidence is ambiguous or blocked by pending decisions, emit no operation for that issue.
Supported operation shapes:
{"op":"noop"}
{"op":"addEntity","name":"EntityName","attributes":[{"name":"attributeName","type":"string"}],"identifier":[{"kind":"attribute|relationship","ref":"attributeOrRelationshipName"}],"inherits_from":["ParentEntityName"]}
{"op":"removeEntity","name":"EntityName"}
{"op":"addAttribute","entity":"EntityName","name":"attributeName","type":"string"}
{"op":"removeAttribute","entity":"EntityName","name":"attributeName"}
{"op":"addRelationship","name":"relationshipName","source":{"entity":"EntityName","multiplicity":"0..1|1|0..*|*|1..*","role":null},"target":{"entity":"EntityName","multiplicity":"0..1|1|0..*|*|1..*","role":null}}
{"op":"removeRelationship","name":"relationshipName","source":"EntityName","target":"EntityName"}
{"op":"setIdentifier","entity":"EntityName","parts":[{"kind":"attribute|relationship","ref":"attributeOrRelationshipName"}]}
{"op":"addInheritance","entity":"SubtypeName","parent":"ParentName"}
{"op":"removeInheritance","entity":"SubtypeName","parent":"ParentName"}
{"op":"renameEntity","old":"OldEntityName","new":"NewEntityName"}
{"op":"renameAttribute","entity":"EntityName","old":"oldAttributeName","new":"newAttributeName"}
{"op":"renameRelationship","old":"oldRelationshipName","new":"newRelationshipName","source":"EntityName","target":"EntityName"}

SPECIFICATION:
{{SPECIFICATION}}

FINDINGS_OR_CHECK_REQUESTS:
{{CRITIC_FINDINGS}}

PENDING_DECISIONS:
{{PENDING_DECISIONS}}

CURRENT_MODEL:
{{STRUCTURED_MODEL}}
"""

LEGACY_PATCH_OPERATION_CLERK_SYSTEM_PROMPT = """\
You emit small conceptual-model patch operations.

Convert critic findings or check/correction requests into deterministic operations for the current JSON IR.
Return only JSONL: one JSON object per line. If no operations are needed, return exactly {"op":"noop"}.
Do not include Markdown, comments, analysis, or extra text.
"""

LEGACY_PATCH_OPERATION_CLERK_USER_TEMPLATE = """\
Task:
Patch CURRENT_MODEL by emitting small operation objects. Do not return the full model.

Operation rules:
- Emit one JSON object per line.
- If the findings/checks do not require a safe operation, emit exactly {"op":"noop"}.
- If a major process area or subdomain from the specification is still missing, prioritize missing-concept and missing-relationship coverage before identifier, lookup, or temporal polish.
- Use entity names from CURRENT_MODEL when modifying existing artifacts.
- Target existing artifacts by their StructuredModel name fields; do not invent or rely on internal generated E/R ids.
- If a relationship needs an entity that is missing, emit addEntity first, then addRelationship later.
- Keep each operation small and idempotent.
- Do not emit both addRelationship and removeRelationship for the same relationship name/endpoints in one batch.
- To change relationship multiplicity or endpoint role, emit addRelationship with the desired endpoint metadata; the deterministic applier updates an existing same-name/same-endpoint relationship.
- Relationship multiplicity convention: multiplicity belongs to the endpoint entity where it appears and is rendered beside that endpoint. It means how many instances of that endpoint entity may be associated with one instance of the opposite endpoint.
- Example: source ParentEntity multiplicity 0..*, target ChildEntity multiplicity 1 means one ChildEntity can have 0..* ParentEntity instances, and one ParentEntity instance has 1 ChildEntity.
- Do not reinterpret source.multiplicity as the number of target instances per source, do not reinterpret target.multiplicity as the number of source instances per target, and do not flip multiplicities globally.
- Change multiplicities only when specification evidence clearly contradicts the existing endpoint cardinality.
- If both existing and proposed cardinalities are defensible for the current entity interpretation, emit no operation.
- Do not remove an existing relationship unless the finding or user request explicitly says it is wrong, redundant, or replaced by an equivalent relationship.
- Do not remove or replace an existing artifact unless the emitted operations preserve the fact it represented or the specification clearly makes it unsupported.
- Use removeEntity only when an entity is explicitly obsolete after a merge/replacement; remove or replace its relationships first.
- Use names in the specification language, normalized to pure ASCII.
- Entity names use UpperCamelCase; attribute and relationship names use lowerCamelCase.
- Attribute type must be one of: string, int, real, bool, date.
- Prefer natural identifiers stated or clearly implied by the specification over surrogate ids.
- Use {"name":"id","type":"int"} only as a fallback identifier for regular concrete entities with no stated or clearly implied natural identifier.
- Never replace or remove an identifier explicitly stated by the specification merely because a different natural/contextual identifier is plausible.
- Subclasses inherit parent identity by default, but may define their own identifier when the specification gives a subtype-specific natural identifier or contextual/weak identifying structure.
- If a parent is only an abstract classification, it may have no identifier.
- When the same participation could be modeled as several role-specific links or as one association entity, use one association entity with role/type and any period/date facts; do not also keep parallel role-specific links for the same fact.
- When extracting lookups, preserve code, required-count, limit, threshold, discriminator, order, line-item, ownership/right, or rule semantics carried by the original scalar/category.
- If removing a scalar/category replaces an identifier, discriminator, order, line-item, ownership/right, status, or type fact, add the replacement relationship and update affected identifiers in the same batch; otherwise do not remove the scalar/category.
- When merging or generalizing repeated item/document/event/line entities, preserve discriminator, order/line-number, quantity, price/amount, status, and contextual identifier facts from the original representation.
- Check that identifier rewrites are complete before removing surrogate ids; if a required identifying relationship is missing and cannot be added safely in this batch, leave the identifier unchanged.
- Check for explicitly stated persistent generated/stored documents, files, or evidence; add them when missing and when they carry facts, identity, lifecycle, or relationships.
- Pending decisions below are unresolved user choices. Do not emit an operation that applies, satisfies, or conflicts with a pending decision.
- If a critic finding overlaps a pending decision but is not the same operation, do not apply it automatically; leave it for the decision system.
- Do not emit speculative corrections. If evidence is ambiguous or blocked by pending decisions, emit no operation for that issue.
Supported operation shapes:
{"op":"noop"}
{"op":"addEntity","name":"EntityName","attributes":[{"name":"attributeName","type":"string"}],"identifier":[{"kind":"attribute|relationship","ref":"attributeOrRelationshipName"}],"inherits_from":["ParentEntityName"]}
{"op":"removeEntity","name":"EntityName"}
{"op":"addAttribute","entity":"EntityName","name":"attributeName","type":"string"}
{"op":"removeAttribute","entity":"EntityName","name":"attributeName"}
{"op":"addRelationship","name":"relationshipName","source":{"entity":"EntityName","multiplicity":"0..1|1|0..*|*|1..*","role":null},"target":{"entity":"EntityName","multiplicity":"0..1|1|0..*|*|1..*","role":null}}
{"op":"removeRelationship","name":"relationshipName","source":"EntityName","target":"EntityName"}
{"op":"setIdentifier","entity":"EntityName","parts":[{"kind":"attribute|relationship","ref":"attributeOrRelationshipName"}]}
{"op":"addInheritance","entity":"SubtypeName","parent":"ParentName"}
{"op":"removeInheritance","entity":"SubtypeName","parent":"ParentName"}
{"op":"renameEntity","old":"OldEntityName","new":"NewEntityName"}
{"op":"renameAttribute","entity":"EntityName","old":"oldAttributeName","new":"newAttributeName"}
{"op":"renameRelationship","old":"oldRelationshipName","new":"newRelationshipName","source":"EntityName","target":"EntityName"}

SPECIFICATION:
{{SPECIFICATION}}

FINDINGS_OR_CHECK_REQUESTS:
{{CRITIC_FINDINGS}}

PENDING_DECISIONS:
{{PENDING_DECISIONS}}

CURRENT_MODEL:
{{STRUCTURED_MODEL}}
"""

UNICODE_NFKC_PATCH_OPERATION_CLERK_USER_TEMPLATE = PATCH_OPERATION_CLERK_USER_TEMPLATE.replace(
    "- Use names in the specification language, normalized to pure ASCII.\n"
    "- Entity names use UpperCamelCase; attribute and relationship names use lowerCamelCase.",
    "- Use names in the specification language and script; never transliterate names to ASCII.\n"
    "- Normalize names with Unicode NFKC and retain Unicode letters, combining marks, and numbers.\n"
    "- Treat punctuation and whitespace as word boundaries. Use UpperCamelCase for entity names and "
    "lowerCamelCase for attribute and relationship names only where the script has case.\n"
    "- Keep Chinese, Japanese, and other uncased-script words unchanged apart from joining word boundaries.\n"
    "- Never emit control characters, formatting characters, surrogates, or bidirectional-control characters in names.",
)

def build_patch_operation_clerk_user_prompt(
    *,
    specification: str,
    coverage_findings_json: str,
    structured_model_json: str,
    pending_decisions_json: str = "",
    template: str = PATCH_OPERATION_CLERK_USER_TEMPLATE,
) -> str:
    return template.replace("{{SPECIFICATION}}", specification).replace(
        "{{CRITIC_FINDINGS}}", coverage_findings_json
    ).replace(
        "{{STRUCTURED_MODEL}}", structured_model_json
    ).replace(
        "{{PENDING_DECISIONS}}", pending_decisions_json or '{"decision_patches": []}'
    )

__all__ = [
    'PATCH_OPERATION_CLERK_SYSTEM_PROMPT',
    'PATCH_OPERATION_CLERK_USER_TEMPLATE',
    'LEGACY_PATCH_OPERATION_CLERK_SYSTEM_PROMPT',
    'LEGACY_PATCH_OPERATION_CLERK_USER_TEMPLATE',
    'UNICODE_NFKC_PATCH_OPERATION_CLERK_USER_TEMPLATE',
    'build_patch_operation_clerk_user_prompt',
]
