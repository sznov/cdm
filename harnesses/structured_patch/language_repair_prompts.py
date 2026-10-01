from __future__ import annotations

STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT = """\
You repair names in a conceptual model.

Return only JSON. Do not include Markdown, comments, analysis, or extra text.
"""

STRUCTURED_LANGUAGE_REPAIR_USER_TEMPLATE = """\
Task:
Check whether model artifact names use the same natural language as the specification.
Return only rename suggestions for names that are translated into another language or clearly not in the specification language.

Important:
- This is a name-only repair pass.
- Do not add, remove, merge, or restructure anything.
- Do not rename merely to prefer a synonym.
- This is not an English-normalization pass.
- Do not translate source-language names into English.
- Accurate English translations are still wrong when the specification uses a non-English term.
- If the current name is in a different language than the specification, propose the closest source-language noun phrase from the specification.
- If a name is already in the specification language, keep it even when it is not English.
- Prefer renaming translated duplicates back toward source-language terms instead of creating more translated names.
- Do not accept English names just because they are standard modeling terminology.
- Keep source-language concepts, normalized to pure ASCII camel case.
- Entity names must be UpperCamelCase ASCII.
- Attribute and relationship names must be lowerCamelCase ASCII.
- If every artifact name already uses the specification language, return an empty renames list.

Return JSON:
{
  "renames": [
    {
      "kind": "entity|attribute|relationship",
      "entity": "entity name for attribute renames, otherwise optional",
      "old": "old name",
      "new": "new name",
      "reason": "short reason"
    }
  ]
}

SPECIFICATION:
{{SPECIFICATION}}

CURRENT_MODEL:
{{STRUCTURED_MODEL}}
"""


def build_structured_language_repair_user_prompt(*, specification: str, structured_model_json: str) -> str:
    return STRUCTURED_LANGUAGE_REPAIR_USER_TEMPLATE.replace("{{SPECIFICATION}}", specification).replace(
        "{{STRUCTURED_MODEL}}", structured_model_json
    )


__all__ = [
    "STRUCTURED_LANGUAGE_REPAIR_SYSTEM_PROMPT",
    "STRUCTURED_LANGUAGE_REPAIR_USER_TEMPLATE",
    "build_structured_language_repair_user_prompt",
]
