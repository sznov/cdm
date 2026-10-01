from __future__ import annotations

MODELING_PLAN_SYSTEM_PROMPT = """\
You are a conceptual data-model planning assistant.

Read the whole natural-language specification and create a modeling plan.
The plan is not the final model and it is not PlantUML.

Return only JSON. Do not include Markdown, comments, analysis, or extra text.
"""

MODELING_PLAN_USER_TEMPLATE = """\
Task:
Extract a phased conceptual-modeling plan from the specification.

The plan should identify modeling obligations that a later modeler must satisfy:
- core entities and their evidence
- likely scalar attributes
- relationships
- reified relationships or association entities
- weak or context-dependent identifiers
- inheritance/generalization groups
- lookup/reference concepts
- important multiplicities or constraints
- open questions where the text is ambiguous

Use the same language as the specification for concept names, but use pure ASCII spelling.
Do not emit final model JSON. Do not emit operations. This is only a checklist.

JSON shape:
{
  "phases": [
    {
      "id": "P1",
      "name": "short phase name",
      "goal": "short phase goal",
      "tasks": [
        {
          "id": "T1",
          "kind": "entity|attribute|relationship|reifiedRelationship|weakIdentifier|inheritance|lookup|multiplicity|constraint|openQuestion",
          "concept": "short concept name or relationship name",
          "participants": ["optional related concepts"],
          "evidence": "short source excerpt",
          "note": "short modeling note"
        }
      ]
    }
  ],
  "open_questions": [
    {
      "topic": "short topic",
      "question": "short question",
      "evidence": "short source excerpt"
    }
  ]
}

SPECIFICATION:
{{SPECIFICATION}}
"""

def build_modeling_plan_user_prompt(*, specification: str) -> str:
    return MODELING_PLAN_USER_TEMPLATE.replace("{{SPECIFICATION}}", specification)

__all__ = [
    'MODELING_PLAN_SYSTEM_PROMPT',
    'MODELING_PLAN_USER_TEMPLATE',
    'build_modeling_plan_user_prompt',
]
