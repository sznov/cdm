from __future__ import annotations

import json
from typing import Any

from core.schemas import StructuredModel

MODEL_QUESTION_SYSTEM_PROMPT = """You answer read-only questions about a saved conceptual modeling run.

Use the provided specification, current model, and surfaced decisions/assumptions.
Do not emit patch operations unless the user explicitly asks for example operations.
Do not mutate the model. If the evidence is unclear, say what is unclear."""

def build_correction_findings_json(message: str) -> str:
    payload = {
        "source": "user_freeform_correction",
        "findings": [
            {
                "id": "USER-CORRECTION-1",
                "severity": "user_requested",
                "kind": "freeformCorrection",
                "summary": "User requested a direct model correction.",
                "suggested_change": message.strip(),
            }
        ],
        "decision_patches": [],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_model_question_user_prompt(
    *,
    question: str,
    specification: str,
    structured_model: StructuredModel | None,
    working_model_payload: dict[str, Any] | None,
    decision_patches: list[dict[str, Any]],
) -> str:
    structured_model_json = (
        json.dumps(structured_model.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if structured_model is not None
        else "(no valid structured model artifact is available)"
    )
    working_model_json = (
        json.dumps(working_model_payload, ensure_ascii=False, indent=2)
        if working_model_payload is not None
        else "(no operation-loop working model artifact is available)"
    )
    decision_patches_json = json.dumps(decision_patches, ensure_ascii=False, indent=2)
    return f"""Task:
Answer the user's question about this saved conceptual-modeling run.

Read-only rules:
- Answer in normal prose.
- Do not produce correction patches, operation JSON, or replacement model JSON unless explicitly asked.
- Ground your answer in the specification and model artifacts below.
- If the model and specification disagree, explain the disagreement.

USER QUESTION:
{question.strip()}

SPECIFICATION:
{specification.strip()}

CURRENT STRUCTURED MODEL:
{structured_model_json}

CURRENT OPERATION-LOOP WORKING MODEL, IF ANY:
{working_model_json}

SURFACED DECISIONS AND ASSUMPTIONS:
{decision_patches_json}
"""


__all__ = [
    "MODEL_QUESTION_SYSTEM_PROMPT",
    "build_correction_findings_json",
    "build_model_question_user_prompt",
]
