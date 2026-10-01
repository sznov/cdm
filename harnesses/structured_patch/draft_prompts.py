from __future__ import annotations

DRAFT_MODEL_SYSTEM_PROMPT = """\
You generate one complete conceptual entity-relationship model JSON object.

Use the modeling plan as a checklist, but the specification is the source of truth.
The output is a draft model: make the best complete model you can, preserve evidence mentally,
and prefer clear conceptual modeling over database implementation details.

Return only JSON. Do not include Markdown, comments, analysis, or extra text.
"""

DRAFT_MODEL_USER_TEMPLATE = """\
Task:
Create a complete conceptual model as one JSON object matching this IR.

Modeling stance:
- Entity = domain concept with identity, lifecycle, relationships, or multiple properties.
- Attribute = scalar property of one entity.
- Relationship = binary association without its own attributes.
- If an association has attributes, period, role, amount, signature, registration, appointment, allocation, or other facts of its own, model it as an entity.
- Model explicitly stated persistent generated/stored documents, files, or evidence as entities when they carry facts, identity, lifecycle, or relationships.
- Prefer maximal spec-grounded data normalization over flattened attributes.
- Treat grouped multi-field noun phrases as candidate entities, especially when they include date, period, status, registration, role, address/location, or can occur multiple times over time.
- Do not invent date, order-number, status, audit, file-path, validation, count, limit, or threshold facts merely because they are useful in a real system; include them only when the specification states or implies stored evidence, tracking, generated files, ordered document/list items, lifecycle, codes, required counts, limits, or thresholds.
- Extract lookup/reference entities for bounded categories, roles, types, statuses, methods, levels, options, classifications, institutions, and other controlled concepts mentioned by the specification.
- If you extract a scalar/type/status into a lookup/reference entity, preserve all meaningful semantics from the source text such as code, required count, limit, threshold, discriminator, order, ownership/right, or rule facts.
- Replace string/scalar attributes with relationships when the value refers to another modeled entity, lookup/reference entity, reusable value object, or clear domain concept.
- Avoid storing the same fact both as a scalar attribute and as a relationship/path; once extracted, keep the normalized relationship representation.
- Keep a scalar attribute flat only when it is intrinsic to exactly one entity and has no identity, lifecycle, history, relationship, reuse, or controlled-vocabulary semantics.
- If a meaningful supertype remains modeled, keep shared names, identifiers, and common properties on the supertype instead of duplicating them only on subtypes.
- Use inherits_from only for true generalization/specialization.
- Do not repeat inherited attributes in subclasses.
- Subclasses inherit parent identity by default.
- A subtype may define its own identifier when the specification gives a subtype-specific natural identifier or a contextual/weak identifying structure.
- If a parent is only an abstract classification, it may have no identifier.
- Use lookup/reference entities for controlled vocabularies when useful.
- Prefer natural identifiers stated or clearly implied by the specification.
- If the text does not specify a natural identifier for a regular concrete entity, use attribute {"name": "id", "type": "int"} as its fallback identifier.
- Use relationship identifier parts for weak/context-dependent concepts when the identifying relationship is present.
- When the same participation could be modeled as several role-specific links or as one association entity, use one association entity with role/type and any period/date facts; do not also keep parallel role-specific links for the same fact.
- Use the same language as the specification for concept names, but pure ASCII identifiers.
- Entity names must be UpperCamelCase ASCII.
- Attribute and relationship names must be lowerCamelCase ASCII.

JSON IR:
{
  "entities": [
    {
      "name": "UpperCamelCaseAsciiName",
      "attributes": [{"name": "lowerCamelCaseAsciiName", "type": "string|int|real|bool|date"}],
      "identifier": [{"kind": "attribute|relationship", "ref": "attributeOrRelationshipName"}],
      "inherits_from": ["ParentEntityName"]
    }
  ],
  "relationships": [
    {
      "name": "lowerCamelCaseAsciiName",
      "source": {"entity": "EntityName", "multiplicity": "0..1|1|0..*|*|1..*", "role": null},
      "target": {"entity": "EntityName", "multiplicity": "0..1|1|0..*|*|1..*", "role": null}
    }
  ]
}

Rules:
- Return one JSON object with exactly "entities" and "relationships".
- Relationship endpoints and inherits_from values must reference existing entity names.
- Identifier attribute refs must reference attributes on the entity or inherited attributes.
- Identifier relationship refs must reference a relationship name touching that entity.
- Do not include evidence fields in the final model JSON.

MODELING_PLAN:
{{MODELING_PLAN}}

SPECIFICATION:
{{SPECIFICATION}}
"""

LEGACY_DRAFT_MODEL_USER_TEMPLATE = DRAFT_MODEL_USER_TEMPLATE.replace(
"""- Prefer maximal spec-grounded data normalization over flattened attributes.
- Treat grouped multi-field noun phrases as candidate entities, especially when they include date, period, status, registration, role, address/location, or can occur multiple times over time.
- Do not invent date, order-number, status, audit, file-path, validation, count, limit, or threshold facts merely because they are useful in a real system; include them only when the specification states or implies stored evidence, tracking, generated files, ordered document/list items, lifecycle, codes, required counts, limits, or thresholds.
- Extract lookup/reference entities for bounded categories, roles, types, statuses, methods, levels, options, classifications, institutions, and other controlled concepts mentioned by the specification.
- If you extract a scalar/type/status into a lookup/reference entity, preserve all meaningful semantics from the source text such as code, required count, limit, threshold, discriminator, order, ownership/right, or rule facts.
- Replace string/scalar attributes with relationships when the value refers to another modeled entity, lookup/reference entity, reusable value object, or clear domain concept.
- Avoid storing the same fact both as a scalar attribute and as a relationship/path; once extracted, keep the normalized relationship representation.
- Keep a scalar attribute flat only when it is intrinsic to exactly one entity and has no identity, lifecycle, history, relationship, reuse, or controlled-vocabulary semantics.
- If a meaningful supertype remains modeled, keep shared names, identifiers, and common properties on the supertype instead of duplicating them only on subtypes.
""",
    "",
)

SIMPLE_DRAFT_SYSTEM_PROMPT = """\
You generate one conceptual entity-relationship model JSON object from a natural-language specification.

Return only JSON. Do not include Markdown, comments, analysis, or extra text.
"""

SIMPLE_DRAFT_USER_TEMPLATE = """\
Task:
Create a conceptual model as one JSON object.

Modeling stance:
- Entity = concept with identity, lifecycle, relationships, or multiple properties.
- Attribute = scalar property of one entity.
- Relationship = binary association without its own attributes.
- If an association has its own date, period, role, amount, signature, registration, appointment, allocation, or other facts, model it as an entity.
- Model explicitly stated persistent generated/stored documents, files, or evidence as entities when they carry facts, identity, lifecycle, or relationships.
- Prefer maximal spec-grounded data normalization over flattened attributes.
- Treat grouped multi-field noun phrases as candidate entities, especially when they include date, period, status, registration, role, address/location, or can occur multiple times over time.
- Do not invent date, order-number, status, audit, file-path, validation, count, limit, or threshold facts merely because they are useful in a real system; include them only when the specification states or implies stored evidence, tracking, generated files, ordered document/list items, lifecycle, codes, required counts, limits, or thresholds.
- Extract lookup/reference entities for bounded categories, roles, types, statuses, methods, levels, options, classifications, institutions, and other controlled concepts mentioned by the specification.
- If you extract a scalar/type/status into a lookup/reference entity, preserve all meaningful semantics from the source text such as code, required count, limit, threshold, discriminator, order, ownership/right, or rule facts.
- Replace string/scalar attributes with relationships when the value refers to another modeled entity, lookup/reference entity, reusable value object, or clear domain concept.
- Avoid storing the same fact both as a scalar attribute and as a relationship/path; once extracted, keep the normalized relationship representation.
- Keep a scalar attribute flat only when it is intrinsic to exactly one entity and has no identity, lifecycle, history, relationship, reuse, or controlled-vocabulary semantics.
- If a meaningful supertype remains modeled, keep shared names, identifiers, and common properties on the supertype instead of duplicating them only on subtypes.
- Use inherits_from only for true generalization/specialization.
- Subclasses inherit parent identity by default.
- A subtype may define its own identifier when the specification gives a subtype-specific natural identifier or a contextual/weak identifying structure.
- If a parent is only an abstract classification, it may have no identifier.
- Prefer natural identifiers stated or clearly implied by the specification.
- If the text gives no natural identifier for a regular concrete entity, use attribute {"name": "id", "type": "int"} as its fallback identifier.
- When the same participation could be modeled as several role-specific links or as one association entity, use one association entity with role/type and any period/date facts; do not also keep parallel role-specific links for the same fact.
- Use the same language as the specification for concept names, normalized to pure ASCII.
- Entity names must be UpperCamelCase. Attribute and relationship names must be lowerCamelCase.

Decision handling:
- Build the initial model from the specification, not from unstated domain assumptions.
- When the specification explicitly states an identifier, use that identifier in the initial model even if real-world domain knowledge suggests extra context.
- When the text states a contextual scope directly, such as a thing numbered "in" another thing, include that context in the identifier.
- If a domain-common relationship or identifier context is only plausible but not stated, do not force it into the initial model.
- If you notice yourself thinking "wait", "maybe", "should probably", "assume", "not sure", "only applies to", or "larger change", surface that as a top-level issue instead of silently choosing.
- Put ambiguous policy choices in top-level issues with kind "decision" instead of forcing them into the initial model.
- Put assumptions you choose to proceed with in top-level issues with kind "assumption".
- Put clear modeling errors you notice in top-level issues with kind "hardError".
- Do not put notes, alternatives, or issue metadata inside entities or relationships.

Pre-return correction checklist:
- Check for semantic errors and correct them if any are found.
- Check for explicitly stated persistent generated/stored documents, files, or evidence; add them when missing and when they carry facts, identity, lifecycle, or relationships.
- Check for one entity conflating several domain concepts; split only when the specification supports the split.
- Check for associations that carry facts such as role, period, appointment, registration, status, employer, amount, signature, or date; model those associations as entities when needed.
- Check for repeated attributes across entities that represent the same fact or concept; normalize them when the shared concept is spec-grounded.
- Check for lookup entity candidates represented as string/scalar attributes; extract clear, persistent controlled concepts.
- When extracting lookups, preserve code, required-count, limit, threshold, discriminator, order, ownership/right, or rule semantics carried by the original scalar/category.
- Check for string/scalar attributes that actually refer to another modeled entity, clear domain concept, reusable value object, or extractable lookup/reference concept.
- Check grouped value attributes such as address/location/residence/contact blocks; extract them when they have multiple fields, own facts, reuse, history, or relationships.
- Check for missing important relationships and relationship multiplicities that contradict the specification.
- Check identifiers: keep stated identifiers, prefer complete spec-derived natural/contextual identifiers, and use surrogate id only when no complete spec-derived identifier satisfies the semantics.
- Check for duplicated information across attributes, relationships, or parallel paths; prefer the normalized representation.
- If a correction is ambiguous, put it in issues instead of silently changing the model.

JSON shape:
{
  "entities": [
    {
      "name": "EntityName",
      "attributes": [{"name": "attributeName", "type": "string|int|real|bool|date"}],
      "identifier": [{"kind": "attribute|relationship", "ref": "attributeOrRelationshipName"}],
      "inherits_from": ["ParentEntityName"]
    }
  ],
  "relationships": [
    {
      "name": "relationshipName",
      "source": {"entity": "EntityName", "multiplicity": "0..1|1|0..*|*|1..*", "role": null},
      "target": {"entity": "EntityName", "multiplicity": "0..1|1|0..*|*|1..*", "role": null}
    }
  ],
  "issues": [
    {
      "kind": "decision|assumption|hardError",
      "target": "artifact being discussed",
      "summary": "short issue",
      "evidence": "short source excerpt or empty string",
      "options": [
        {"label": "short option", "patch": null},
        {"label": "short option", "patch": {"op": "setIdentifier", "entity": "EntityName", "parts": [{"kind": "relationship", "ref": "relationshipName"}, {"kind": "attribute", "ref": "attributeName"}]}}
      ]
    }
  ]
}

Rules:
- Return one JSON object with "entities", "relationships", and optional "issues".
- Use issues for any unresolved or assumed modeling choice you noticed while creating the model.
- Relationship endpoints and inherits_from values must reference existing entity names.
- Identifier attribute refs must reference attributes on the entity or inherited attributes.
- Identifier relationship refs must reference a relationship name touching that entity.
- Do not include evidence fields inside entities, relationships, attributes, identifiers, or relationship ends.

SPECIFICATION:
{{SPECIFICATION}}
"""

LEGACY_SIMPLE_DRAFT_USER_TEMPLATE = """\
Task:
Create a conceptual model as one JSON object.

Modeling stance:
- Entity = concept with identity, lifecycle, relationships, or multiple properties.
- Attribute = scalar property of one entity.
- Relationship = binary association without its own attributes.
- If an association has its own date, period, role, amount, signature, registration, appointment, allocation, or other facts, model it as an entity.
- Model explicitly stated persistent generated/stored documents, files, or evidence as entities when they carry facts, identity, lifecycle, or relationships.
- Use inherits_from only for true generalization/specialization.
- Subclasses inherit parent identity by default.
- A subtype may define its own identifier when the specification gives a subtype-specific natural identifier or a contextual/weak identifying structure.
- If a parent is only an abstract classification, it may have no identifier.
- Prefer natural identifiers stated or clearly implied by the specification.
- If the text gives no natural identifier for a regular concrete entity, use attribute {"name": "id", "type": "int"} as its fallback identifier.
- When the same participation could be modeled as several role-specific links or as one association entity, use one association entity with role/type and any period/date facts; do not also keep parallel role-specific links for the same fact.
- Use the same language as the specification for concept names, normalized to pure ASCII.
- Entity names must be UpperCamelCase. Attribute and relationship names must be lowerCamelCase.

Decision handling:
- Build the initial model from the specification, not from unstated domain assumptions.
- When the specification explicitly states an identifier, use that identifier in the initial model even if real-world domain knowledge suggests extra context.
- When the text states a contextual scope directly, such as a thing numbered "in" another thing, include that context in the identifier.
- If a domain-common relationship or identifier context is only plausible but not stated, do not force it into the initial model.
- If you notice yourself thinking "wait", "maybe", "should probably", "assume", "not sure", "only applies to", or "larger change", surface that as a top-level issue instead of silently choosing.
- Put ambiguous policy choices in top-level issues with kind "decision" instead of forcing them into the initial model.
- Put assumptions you choose to proceed with in top-level issues with kind "assumption".
- Put clear modeling errors you notice in top-level issues with kind "hardError".
- Do not put notes, alternatives, or issue metadata inside entities or relationships.

JSON shape:
{
  "entities": [
    {
      "name": "EntityName",
      "attributes": [{"name": "attributeName", "type": "string|int|real|bool|date"}],
      "identifier": [{"kind": "attribute|relationship", "ref": "attributeOrRelationshipName"}],
      "inherits_from": ["ParentEntityName"]
    }
  ],
  "relationships": [
    {
      "name": "relationshipName",
      "source": {"entity": "EntityName", "multiplicity": "0..1|1|0..*|*|1..*", "role": null},
      "target": {"entity": "EntityName", "multiplicity": "0..1|1|0..*|*|1..*", "role": null}
    }
  ],
  "issues": [
    {
      "kind": "decision|assumption|hardError",
      "target": "artifact being discussed",
      "summary": "short issue",
      "evidence": "short source excerpt or empty string",
      "options": [
        {"label": "short option", "patch": null},
        {"label": "short option", "patch": {"op": "setIdentifier", "entity": "EntityName", "parts": [{"kind": "relationship", "ref": "relationshipName"}, {"kind": "attribute", "ref": "attributeName"}]}}
      ]
    }
  ]
}

Rules:
- Return one JSON object with "entities", "relationships", and optional "issues".
- Use issues for any unresolved or assumed modeling choice you noticed while creating the model.
- Relationship endpoints and inherits_from values must reference existing entity names.
- Identifier attribute refs must reference attributes on the entity or inherited attributes.
- Identifier relationship refs must reference a relationship name touching that entity.
- Do not include evidence fields inside entities, relationships, attributes, identifiers, or relationship ends.

SPECIFICATION:
{{SPECIFICATION}}
"""

UNICODE_NFKC_NAME_INSTRUCTIONS = """\
- Use the same language and script as the specification for concept names; never transliterate names to ASCII.
- Normalize names with Unicode NFKC. Retain Unicode letters, combining marks, and numbers.
- Treat punctuation and whitespace as word boundaries.
- Use UpperCamelCase for entity names and lowerCamelCase for attribute and relationship names where the script has case.
- Keep Chinese, Japanese, and other uncased-script words unchanged apart from joining word boundaries.
- Never emit control characters, formatting characters, surrogates, or bidirectional-control characters in names.
""".rstrip()

UNICODE_NFKC_SIMPLE_DRAFT_USER_TEMPLATE = SIMPLE_DRAFT_USER_TEMPLATE.replace(
    "- Use the same language as the specification for concept names, normalized to pure ASCII.\n"
    "- Entity names must be UpperCamelCase. Attribute and relationship names must be lowerCamelCase.",
    UNICODE_NFKC_NAME_INSTRUCTIONS,
)

def build_draft_model_user_prompt(
    *,
    specification: str,
    modeling_plan_json: str,
    template: str = DRAFT_MODEL_USER_TEMPLATE,
) -> str:
    return template.replace("{{SPECIFICATION}}", specification).replace(
        "{{MODELING_PLAN}}", modeling_plan_json
    )

def build_simple_draft_user_prompt(
    *,
    specification: str,
    template: str = SIMPLE_DRAFT_USER_TEMPLATE,
) -> str:
    return template.replace("{{SPECIFICATION}}", specification)

def format_draft_model_retry_feedback(*, error: str, raw_output: str) -> str:
    return (
        "Your draft model failed deterministic validation.\n\n"
        f"Validation error:\n{error}\n\n"
        "Return the full corrected JSON model only. Preserve valid parts where possible. "
        "Do not include Markdown, comments, explanations, evidence fields, or trailing commas.\n\n"
        "Previous output:\n"
        f"{raw_output}"
    )

__all__ = [
    'DRAFT_MODEL_SYSTEM_PROMPT',
    'DRAFT_MODEL_USER_TEMPLATE',
    'LEGACY_DRAFT_MODEL_USER_TEMPLATE',
    'SIMPLE_DRAFT_SYSTEM_PROMPT',
    'SIMPLE_DRAFT_USER_TEMPLATE',
    'LEGACY_SIMPLE_DRAFT_USER_TEMPLATE',
    'UNICODE_NFKC_NAME_INSTRUCTIONS',
    'UNICODE_NFKC_SIMPLE_DRAFT_USER_TEMPLATE',
    'build_draft_model_user_prompt',
    'build_simple_draft_user_prompt',
    'format_draft_model_retry_feedback',
]
