from __future__ import annotations

PLAN_COVERAGE_CRITIC_SYSTEM_PROMPT = """\
You are a spec-aware conceptual-model coverage critic.

Compare the modeling plan and current conceptual model against the specification.
Find important missing, conflated, unsupported, or weakly modeled conceptual artifacts.

Return only JSON. Do not include Markdown, comments, analysis, or extra text.
"""

PLAN_COVERAGE_CRITIC_USER_TEMPLATE = """\
Task:
Review the current model after the initial draft pass.
Return concise findings that a later patch planner or operation clerk can turn into small modeling edits.

Rules:
- Focus on conceptual ER modeling gaps, not physical database implementation.
- Prefer high-impact missing concepts, missing relationships, weak identifiers, reified relationships, inheritance gaps, normalization gaps, and lookup/reference gaps.
- If a major process area or subdomain is still missing, prioritize that coverage gap before identifier, lookup, or temporal polish on already-modeled concepts.
- Prefer maximal spec-grounded data normalization: flag flattened scalar/string attributes when they should be entities, lookups, reusable value objects, or relationships.
- Treat grouped multi-field noun phrases as candidate entities, especially when they include date, period, status, registration, role, address/location, or can occur multiple times over time.
- Do not flag missing date, order-number, status, audit, file-path, validation, count, limit, or threshold facts unless the specification states or implies stored evidence, tracking, generated files, ordered document/list items, lifecycle, codes, required counts, limits, or thresholds.
- When flagging lookup/reference extraction, require preserving any code, required count, limit, threshold, discriminator, order, line-item, ownership/right, or rule facts tied to the original scalar/category values, including identifier updates when the scalar helped identify or distinguish instances.
- Flag cases where a shared name, identifier, or common property was pushed down into subtypes while a meaningful supertype remains modeled.
- Flag duplicated facts represented across attributes, relationships, or parallel paths; prefer one normalized representation.
- When the same participation could be modeled as several role-specific links or as one association/event entity, use one association/event entity with role/type and any period/date facts; do not also keep parallel role-specific links for the same fact.
- Use the modeling plan task ids when a finding corresponds to a task.
- Do not assume any reference model beyond the visible specification, plan, and current model.
- Keep each suggested_change small enough to become one or a few operations.
- If you notice yourself thinking "wait", "maybe", "should probably", "assume", "not sure", "only applies to", or "larger change", surface that as a decision patch or assumption instead of silently choosing.
- If a finding is a policy choice rather than an automatic correction, put it in decision_patches instead of findings.
- Decision patches are user-approved optional operations for ambiguous modeling choices such as literal identifier text vs contextual real-world uniqueness.
- Pending decisions below are already surfaced for human review. Do not repeat them as findings.
- If a gap appears to overlap a pending decision, add evidence to a new decision patch only when it is materially different; otherwise omit it.
- If the item is only an assumption to record, put it in decision_patches with kind "assumption" and operation null.
- Only include a decision patch operation when you can fill the complete operation from CURRENT_MODEL.
- If you cannot fill the complete operation, describe the choice in a finding or issue, but set no operation.
- Return at most 12 findings.

Identifier policy:
{{IDENTIFIER_POLICY}}

PENDING_DECISIONS:
{{PENDING_DECISIONS}}

Return JSON:
{
  "findings": [
    {
      "id": "F1",
      "severity": "high|medium|low",
      "kind": "missingConcept|missingRelationship|missingIdentifier|missingInheritance|missingLookup|conflation|unsupported|naming|other",
      "plan_task_id": "T1 or empty string",
      "summary": "short finding",
      "evidence": "short source excerpt or plan evidence",
      "suggested_change": "operation-sized change request"
    }
  ],
  "decision_patches": [
    {
      "id": "DP1",
      "kind": "modelingDecision|assumption",
      "title": "short user-facing decision or assumption title",
      "question": "short question the user can decide, or assumption statement to review",
      "reason": "why this is a legitimate modeling decision or assumption",
      "evidence": "short source excerpt or empty string",
      "operation": {"op": "setIdentifier", "entity": "EntityName", "parts": [{"kind": "relationship", "ref": "relationshipName"}, {"kind": "attribute", "ref": "attributeName"}]}
    }
  ]
}

SPECIFICATION:
{{SPECIFICATION}}

MODELING_PLAN:
{{MODELING_PLAN}}

CURRENT_MODEL:
{{STRUCTURED_MODEL}}
"""

LEGACY_PLAN_COVERAGE_CRITIC_USER_TEMPLATE = """\
Task:
Review the current model after the initial draft pass.
Return concise findings that a later patch planner or operation clerk can turn into small modeling edits.

Rules:
- Focus on conceptual ER modeling gaps, not physical database implementation.
- Prefer high-impact missing concepts, missing relationships, weak identifiers, reified relationships, inheritance gaps, lookup/reference gaps, and explicitly stated generated/stored documents, files, or evidence.
- If a major process area or subdomain from the specification is still missing, prioritize that coverage gap before identifier, lookup, or temporal polish on already-modeled concepts.
- When the same participation could be modeled as several role-specific links or as one association/event entity, use one association/event entity with role/type and any period/date facts; do not also keep parallel role-specific links for the same fact.
- When flagging lookup/reference extraction, require preserving any code, required count, limit, threshold, or rule facts tied to the original scalar/category values.
- Use the modeling plan task ids when a finding corresponds to a task.
- Do not assume any reference model beyond the visible specification, plan, and current model.
- Keep each suggested_change small enough to become one or a few operations.
- If you notice yourself thinking "wait", "maybe", "should probably", "assume", "not sure", "only applies to", or "larger change", surface that as a decision patch or assumption instead of silently choosing.
- If a finding is a policy choice rather than an automatic correction, put it in decision_patches instead of findings.
- Decision patches are user-approved optional operations for ambiguous modeling choices such as literal identifier text vs contextual real-world uniqueness.
- Pending decisions below are already surfaced for human review. Do not repeat them as findings.
- If a gap appears to overlap a pending decision, add evidence to a new decision patch only when it is materially different; otherwise omit it.
- If the item is only an assumption to record, put it in decision_patches with kind "assumption" and operation null.
- Only include a decision patch operation when you can fill the complete operation from CURRENT_MODEL.
- If you cannot fill the complete operation, describe the choice in a finding or issue, but set no operation.
- Return at most 12 findings.

Identifier policy:
{{IDENTIFIER_POLICY}}

PENDING_DECISIONS:
{{PENDING_DECISIONS}}

Return JSON:
{
  "findings": [
    {
      "id": "F1",
      "severity": "high|medium|low",
      "kind": "missingConcept|missingRelationship|missingIdentifier|missingInheritance|missingLookup|conflation|unsupported|naming|other",
      "plan_task_id": "T1 or empty string",
      "summary": "short finding",
      "evidence": "short source excerpt or plan evidence",
      "suggested_change": "operation-sized change request"
    }
  ],
  "decision_patches": [
    {
      "id": "DP1",
      "kind": "modelingDecision|assumption",
      "title": "short user-facing decision or assumption title",
      "question": "short question the user can decide, or assumption statement to review",
      "reason": "why this is a legitimate modeling decision or assumption",
      "evidence": "short source excerpt or empty string",
      "operation": {"op": "setIdentifier", "entity": "EntityName", "parts": [{"kind": "relationship", "ref": "relationshipName"}, {"kind": "attribute", "ref": "attributeName"}]}
    }
  ]
}

SPECIFICATION:
{{SPECIFICATION}}

MODELING_PLAN:
{{MODELING_PLAN}}

CURRENT_MODEL:
{{STRUCTURED_MODEL}}
"""

def literal_identifier_policy_text() -> str:
    return (
        "Literal mode. If the specification explicitly states an identifier, treat it as sufficient unless "
        "the specification itself contradicts it. Do not strengthen identifiers using outside domain assumptions."
    )

def infer_implicit_identifier_policy_text() -> str:
    return (
        "Contextual-inference mode. If an explicit identifier appears under-specified for real-world uniqueness "
        "and the specification also states a contextual owner/location/event relationship, you may flag or accept "
        "a minimal identifying relationship. Prefer natural/contextual identifiers over surrogate ids. "
        "Subclasses inherit parent identity by default, but may define a subtype-specific identifier when the "
        "specification states or clearly implies one. Keep it evidence-based and avoid pure domain guessing."
    )

def identifier_policy_text(*, infer_implicit_identifiers: bool) -> str:
    return infer_implicit_identifier_policy_text() if infer_implicit_identifiers else literal_identifier_policy_text()

def build_plan_coverage_critic_user_prompt(
    *,
    specification: str,
    modeling_plan_json: str,
    structured_model_json: str,
    identifier_policy: str = "",
    pending_decisions_json: str = "",
    template: str = PLAN_COVERAGE_CRITIC_USER_TEMPLATE,
) -> str:
    return template.replace("{{SPECIFICATION}}", specification).replace(
        "{{MODELING_PLAN}}", modeling_plan_json
    ).replace(
        "{{STRUCTURED_MODEL}}", structured_model_json
    ).replace(
        "{{IDENTIFIER_POLICY}}", identifier_policy or literal_identifier_policy_text()
    ).replace(
        "{{PENDING_DECISIONS}}", pending_decisions_json or '{"decision_patches": []}'
    )

__all__ = [
    'PLAN_COVERAGE_CRITIC_SYSTEM_PROMPT',
    'PLAN_COVERAGE_CRITIC_USER_TEMPLATE',
    'LEGACY_PLAN_COVERAGE_CRITIC_USER_TEMPLATE',
    'literal_identifier_policy_text',
    'infer_implicit_identifier_policy_text',
    'identifier_policy_text',
    'build_plan_coverage_critic_user_prompt',
]
