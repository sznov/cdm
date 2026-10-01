from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.api.models import CorrectionPatchRequest
from backend.persistence.session_chat import session_comments_context
from harnesses.structured_patch.patch_prompts import build_patch_operation_clerk_user_prompt
from harnesses.structured_patch.patch_prompts import PATCH_OPERATION_CLERK_USER_TEMPLATE
from core.schemas import StructuredModel
from backend.services.correction_prompts import build_correction_findings_json


@dataclass(slots=True)
class CorrectionPatchPrompt:
    user_prompt: str
    messages: list[dict[str, str]]
    allowed_ops: set[str]


def build_freeform_correction_patch_prompt(
    *,
    request: CorrectionPatchRequest,
    message: str,
    specification: str,
    model: StructuredModel,
    session_id: str | None,
    sessions_dir: Path,
    prompt_template: str = PATCH_OPERATION_CLERK_USER_TEMPLATE,
) -> CorrectionPatchPrompt:
    structured_model_json = json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2)
    correction_findings_json = build_correction_findings_json(message)
    user_prompt = build_patch_operation_clerk_user_prompt(
        specification=specification,
        coverage_findings_json=correction_findings_json,
        structured_model_json=structured_model_json,
        template=prompt_template,
    )
    session_context = session_comments_context(session_id, sessions_dir=sessions_dir)
    if session_context:
        user_prompt += f"\n\nSESSION CONTEXT FROM USER COMMENTS AND CHAT:\n{session_context}\n"
    if request.max_operations is None:
        if "Stop after at most 12 operations." in user_prompt:
            user_prompt = user_prompt.replace(
                "Stop after at most 12 operations.",
                "Emit all operations needed for the requested correction.",
            )
        else:
            user_prompt += "\nEmit all operations needed for the requested correction.\n"
    else:
        if "Stop after at most 12 operations." in user_prompt:
            user_prompt = user_prompt.replace(
                "Stop after at most 12 operations.",
                f"Stop after at most {request.max_operations} operations.",
            )
        else:
            user_prompt += f"\nStop after at most {request.max_operations} operations.\n"
    allowed_ops = {str(op).strip() for op in (request.allowed_ops or []) if str(op).strip()}
    if allowed_ops:
        allowed_ops_list = ", ".join(sorted(allowed_ops))
        user_prompt += (
            "\nFor this correction request, allowed operation op values are: "
            f"{allowed_ops_list}. If the check finds no issue, or if a correct fix would require any "
            'other operation type, emit exactly {"op":"noop"}.\n'
        )
    messages = [{"role": "user", "content": user_prompt}]
    return CorrectionPatchPrompt(user_prompt=user_prompt, messages=messages, allowed_ops=allowed_ops)
