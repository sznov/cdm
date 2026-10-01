from __future__ import annotations

from dataclasses import dataclass

from harnesses.structured_patch.draft_prompts import (
    SIMPLE_DRAFT_SYSTEM_PROMPT,
    SIMPLE_DRAFT_USER_TEMPLATE,
)


SCHEMA_ONLY_SYSTEM_PROMPT = """\
You convert requirements specifications into JSON conceptual models.

Return only valid JSON. Do not include Markdown, comments, analysis, or extra text.
"""


SCHEMA_ONLY_USER_TEMPLATE = """\
Convert the following requirements specification into a JSON conceptual model.

Return only valid JSON matching this schema:

{
  "entities": [
    {
      "name": "EntityName",
      "attributes": [
        { "name": "attributeName", "type": "string" }
      ],
      "identifier": [
        { "kind": "attribute", "ref": "attributeName" },
        { "kind": "relationship", "ref": "relationshipName" }
      ],
      "inherits_from": ["ParentEntityName"]
    }
  ],
  "relationships": [
    {
      "name": "relationshipName",
      "source": {
        "entity": "EntityName",
        "multiplicity": "1"
      },
      "target": {
        "entity": "OtherEntityName",
        "multiplicity": "0..*"
      }
    }
  ]
}

Rules:
- Return JSON only.
- Do not include explanations, Markdown, comments, or extra top-level keys.
- Use only these attribute types: string, int, real, bool, date.
- Use only these multiplicities: 0..1, 1, 0..*, 1..*.
- Every identifier ref must refer to an attribute name or relationship name in the model.
- Every relationship endpoint entity must refer to an entity in the model.

Specification:
<<<
{{SPECIFICATION}}
>>>
"""


@dataclass(frozen=True, slots=True)
class DirectPromptProfile:
    id: str
    template_id: str
    system_prompt: str
    user_template: str


DIRECT_PROMPT_PROFILES: dict[str, DirectPromptProfile] = {
    "schema_only_v1": DirectPromptProfile(
        id="schema_only_v1",
        template_id="simple_prompt_baseline_v1_schema_only",
        system_prompt=SCHEMA_ONLY_SYSTEM_PROMPT,
        user_template=SCHEMA_ONLY_USER_TEMPLATE,
    ),
    "structured_draft_with_issues": DirectPromptProfile(
        id="structured_draft_with_issues",
        template_id="structured_draft_with_issues_v1",
        system_prompt=SIMPLE_DRAFT_SYSTEM_PROMPT,
        user_template=SIMPLE_DRAFT_USER_TEMPLATE,
    ),
}

DIRECT_PROMPT_TEMPLATE_REVISIONS = {
    "schema_only_v1": "simple-prompt-baseline-v1-schema-only-r1",
    "structured_draft_with_issues": "structured-draft-with-issues-v1-r1",
}


def direct_prompt_profile(profile_id: str | None) -> DirectPromptProfile:
    resolved = (profile_id or "schema_only_v1").strip() or "schema_only_v1"
    try:
        return DIRECT_PROMPT_PROFILES[resolved]
    except KeyError as exc:
        options = ", ".join(sorted(DIRECT_PROMPT_PROFILES))
        raise ValueError(f"Unknown direct prompt profile {resolved!r}. Expected one of: {options}") from exc


def build_direct_user_prompt(*, specification: str, prompt_profile: DirectPromptProfile) -> str:
    return prompt_profile.user_template.replace("{{SPECIFICATION}}", specification)


__all__ = [
    "DIRECT_PROMPT_PROFILES",
    "DIRECT_PROMPT_TEMPLATE_REVISIONS",
    "DirectPromptProfile",
    "SCHEMA_ONLY_SYSTEM_PROMPT",
    "SCHEMA_ONLY_USER_TEMPLATE",
    "build_direct_user_prompt",
    "direct_prompt_profile",
]
