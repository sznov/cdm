from __future__ import annotations

from harnesses.structured_patch.coverage_prompts import literal_identifier_policy_text

CRITIC_MODEL_PATCH_SYSTEM_PROMPT = """\
You patch a conceptual entity-relationship model JSON object.

Use the critic findings as a bounded edit brief. Preserve valid existing model elements unless a finding directly
requires changing them.

Return only JSON. Do not include Markdown, comments, analysis, or extra text.
"""

CRITIC_MODEL_PATCH_USER_TEMPLATE = """\
Task:
Patch the current conceptual model to address the critic findings.

Rules:
- Return the complete corrected JSON model, not a diff.
- Use the same JSON IR shape as CURRENT_MODEL.
- Prefer fixing high and medium severity findings first.
- Keep valid existing entities, attributes, identifiers, inheritance, relationships, multiplicities, and roles.
- You may add missing entities, attributes, inheritance, and relationships when supported by the specification.
- Do not add evidence fields.
- If a finding is uncertain or cannot be fixed cleanly, leave the model unchanged for that finding.
- Relationship endpoints and inherits_from values must reference existing entity names.
- Identifier attribute refs must reference attributes on the entity or inherited attributes.
- Identifier relationship refs must reference a relationship name touching that entity.

SPECIFICATION:
{{SPECIFICATION}}

MODELING_PLAN:
{{MODELING_PLAN}}

FINDINGS_OR_CHECK_REQUESTS:
{{CRITIC_FINDINGS}}

CURRENT_MODEL:
{{STRUCTURED_MODEL}}
"""

CRITIC_PATCH_TASK_PLANNER_SYSTEM_PROMPT = """\
You plan small conceptual-model repair tasks.

Convert critic findings into an ordered queue of atomic patch tasks. Each task should be small enough for a
separate model call to apply and for a deterministic validator to accept or reject.

Return only JSON. Do not include Markdown, comments, analysis, or extra text.
"""

CRITIC_PATCH_TASK_PLANNER_USER_TEMPLATE = """\
Task:
Turn the coverage critic findings into a short ordered patch queue.

Rules:
- Use only the specification, modeling plan, current model, and critic findings.
- Prefer high-impact missing concepts, relationships, identifiers, inheritance, and conflation fixes.
- Keep each task to one conceptual edit or one tightly coupled prerequisite edit.
- Order prerequisites first: missing entity before relationships, inheritance, or identifiers that need it.
- Avoid duplicate work already present in CURRENT_MODEL.
- Return at most 8 tasks.

Return JSON:
{
  "tasks": [
    {
      "id": "PT1",
      "finding_id": "F1",
      "kind": "addEntity|addRelationship|addAttribute|fixIdentifier|fixInheritance|rename|removeUnsupported|other",
      "target": "artifact or concept to change",
      "summary": "one atomic modeling edit",
      "allowed_scope": ["artifact names that may change"],
      "evidence": "short source excerpt or critic evidence"
    }
  ]
}

SPECIFICATION:
{{SPECIFICATION}}

MODELING_PLAN:
{{MODELING_PLAN}}

FINDINGS_OR_CHECK_REQUESTS:
{{CRITIC_FINDINGS}}

CURRENT_MODEL:
{{STRUCTURED_MODEL}}
"""

ATOMIC_MODEL_PATCH_SYSTEM_PROMPT = """\
You apply one small conceptual-model patch task to a JSON entity-relationship model.

Make the smallest valid model change that satisfies the task. Preserve unrelated model elements.

Return only JSON. Do not include Markdown, comments, analysis, or extra text.
"""

ATOMIC_MODEL_PATCH_USER_TEMPLATE = """\
Task:
Apply exactly this one patch task to CURRENT_MODEL.

Rules:
- Return the complete corrected JSON model, not a diff.
- Use the same JSON IR shape as CURRENT_MODEL.
- Preserve unrelated entities, attributes, identifiers, inheritance, relationships, multiplicities, and roles.
- Make only the requested atomic edit or its minimum prerequisite.
- Use the same natural language as the specification, normalized to pure ASCII names.
- Entity names use UpperCamelCase; attributes and relationships use lowerCamelCase.
- Use attributes with type string, int, real, bool, or date.
- Do not add evidence fields.
- Relationship endpoints and inherits_from values must reference existing entity names in the returned model.
- Identifier attribute refs must reference attributes on the entity or inherited attributes.
- Identifier relationship refs must reference a relationship name touching that entity.
- If the task cannot be cleanly applied from the available context, return CURRENT_MODEL unchanged.

SPECIFICATION:
{{SPECIFICATION}}

MODELING_PLAN:
{{MODELING_PLAN}}

PATCH_TASK:
{{PATCH_TASK}}

CURRENT_MODEL:
{{STRUCTURED_MODEL}}
"""

SEMANTIC_PATCH_VALIDATOR_SYSTEM_PROMPT = """\
You validate one proposed conceptual-model patch against the specification.

Decide whether the patch is conceptually justified, scoped to the patch task, and not a duplicate or unsupported
modeling edit.

Return only JSON. Do not include Markdown, comments, analysis, or extra text.
"""

SEMANTIC_PATCH_VALIDATOR_USER_TEMPLATE = """\
Task:
Validate whether the proposed patch should be accepted.

Rules:
- Accept only if the patch is supported by the specification or is a necessary generic modeling repair.
- Reject if the patch changes unrelated model elements, duplicates an existing concept, adds unsupported semantics, uses the wrong language, or fails to satisfy the patch task.
- Reject lookup extraction that loses code, required-count, limit, threshold, or rule semantics carried by the original scalar/category.
- Reject lookup extraction that removes a scalar/category which identifies, orders, classifies, or distinguishes instances
  unless the patch adds the replacement relationship and updates the affected identifier or equivalent constraint.
- Reject patches that push a shared name, identifier, or common property down into subtypes while removing it from a meaningful supertype, unless the specification gives subtype-specific semantics.
- Reject identifier rewrites that remove a surrogate before the complete spec-derived identifying attributes/relationships exist in the model.
- Reject identifier rewrites that replace or remove an identifier explicitly stated by the specification merely because a different natural/contextual identifier is plausible.
- Reject multiplicity-only changes when the current and proposed cardinalities are both defensible for the current entity interpretation.
- Reject merges or generalizations of repeated item/document/event/line entities that lose discriminator, order/line-number, quantity, amount, status, or contextual identifier facts.
- Reject added date, order-number, status, audit, file-path, validation, count, limit, or threshold facts when they are only plausible implementation details and not stated or implied by the specification.
- Prefer conceptual ER modeling quality over physical database implementation details.
- Use evidence from the specification when possible.
- Keep the retry_instruction short and actionable.

Identifier policy:
{{IDENTIFIER_POLICY}}

Return JSON:
{
  "decision": "accept|reject",
  "reason": "short reason",
  "evidence": "short source excerpt or empty string",
  "problems": ["short problem"],
  "retry_instruction": "short instruction for a corrected patch"
}

SPECIFICATION:
{{SPECIFICATION}}

PATCH_TASK:
{{PATCH_TASK}}

MODEL_DELTA:
{{MODEL_DELTA}}

BEFORE_LOCAL_CONTEXT:
{{BEFORE_LOCAL_CONTEXT}}

AFTER_LOCAL_CONTEXT:
{{AFTER_LOCAL_CONTEXT}}
"""

def build_critic_model_patch_user_prompt(
    *,
    specification: str,
    modeling_plan_json: str,
    coverage_findings_json: str,
    structured_model_json: str,
) -> str:
    return CRITIC_MODEL_PATCH_USER_TEMPLATE.replace("{{SPECIFICATION}}", specification).replace(
        "{{MODELING_PLAN}}", modeling_plan_json
    ).replace(
        "{{CRITIC_FINDINGS}}", coverage_findings_json
    ).replace(
        "{{STRUCTURED_MODEL}}", structured_model_json
    )

def build_critic_patch_task_planner_user_prompt(
    *,
    specification: str,
    modeling_plan_json: str,
    coverage_findings_json: str,
    structured_model_json: str,
) -> str:
    return CRITIC_PATCH_TASK_PLANNER_USER_TEMPLATE.replace("{{SPECIFICATION}}", specification).replace(
        "{{MODELING_PLAN}}", modeling_plan_json
    ).replace(
        "{{CRITIC_FINDINGS}}", coverage_findings_json
    ).replace(
        "{{STRUCTURED_MODEL}}", structured_model_json
    )

def build_atomic_model_patch_user_prompt(
    *,
    specification: str,
    modeling_plan_json: str,
    patch_task_json: str,
    structured_model_json: str,
) -> str:
    return ATOMIC_MODEL_PATCH_USER_TEMPLATE.replace("{{SPECIFICATION}}", specification).replace(
        "{{MODELING_PLAN}}", modeling_plan_json
    ).replace(
        "{{PATCH_TASK}}", patch_task_json
    ).replace(
        "{{STRUCTURED_MODEL}}", structured_model_json
    )

def build_semantic_patch_validator_user_prompt(
    *,
    specification: str,
    patch_task_json: str,
    model_delta_json: str,
    before_local_context_json: str,
    after_local_context_json: str,
    identifier_policy: str = "",
) -> str:
    return SEMANTIC_PATCH_VALIDATOR_USER_TEMPLATE.replace("{{SPECIFICATION}}", specification).replace(
        "{{PATCH_TASK}}", patch_task_json
    ).replace(
        "{{MODEL_DELTA}}", model_delta_json
    ).replace(
        "{{BEFORE_LOCAL_CONTEXT}}", before_local_context_json
    ).replace(
        "{{AFTER_LOCAL_CONTEXT}}", after_local_context_json
    ).replace(
        "{{IDENTIFIER_POLICY}}", identifier_policy or literal_identifier_policy_text()
    )

__all__ = [
    'CRITIC_MODEL_PATCH_SYSTEM_PROMPT',
    'CRITIC_MODEL_PATCH_USER_TEMPLATE',
    'CRITIC_PATCH_TASK_PLANNER_SYSTEM_PROMPT',
    'CRITIC_PATCH_TASK_PLANNER_USER_TEMPLATE',
    'ATOMIC_MODEL_PATCH_SYSTEM_PROMPT',
    'ATOMIC_MODEL_PATCH_USER_TEMPLATE',
    'SEMANTIC_PATCH_VALIDATOR_SYSTEM_PROMPT',
    'SEMANTIC_PATCH_VALIDATOR_USER_TEMPLATE',
    'build_critic_model_patch_user_prompt',
    'build_critic_patch_task_planner_user_prompt',
    'build_atomic_model_patch_user_prompt',
    'build_semantic_patch_validator_user_prompt',
]
