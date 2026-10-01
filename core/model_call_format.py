from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.config_safety import (
    redact_persisted_value,
    redact_sensitive_text,
    safe_exception_detail,
)
from core.model_client import ChatMessage, CompletionResult


def format_chat_messages_for_log(
    *,
    system_prompt: str,
    user_content: str,
    messages: list[ChatMessage] | None,
) -> list[ChatMessage]:
    chat_messages: list[ChatMessage] = [{"role": "system", "content": system_prompt}]
    if messages is None:
        chat_messages.append({"role": "user", "content": user_content})
    else:
        chat_messages.extend({"role": item["role"], "content": item["content"]} for item in messages)
    return chat_messages


def format_model_call_log(
    *,
    job_id: str,
    call_index: int,
    kind: str,
    system_prompt: str,
    user_content: str,
    messages: list[ChatMessage] | None,
    completion: CompletionResult | None,
    error: BaseException | None,
    metadata: dict[str, Any],
) -> str:
    chat_messages = format_chat_messages_for_log(
        system_prompt=system_prompt,
        user_content=user_content,
        messages=messages,
    )
    lines = [
        f"JOB ID: {job_id}",
        f"CALL INDEX: {call_index}",
        f"CALL KIND: {kind}",
        f"TIMESTAMP UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "=== METADATA ===",
        json.dumps(redact_persisted_value(metadata), ensure_ascii=False, indent=2),
        "",
        "=== FULL CHAT PROMPT ===",
    ]
    for index, message in enumerate(chat_messages, start=1):
        lines.extend(
            [
                "",
                f"--- MESSAGE {index}: {message['role'].upper()} ---",
                message["content"],
            ]
        )
    lines.extend(
        [
            "",
            "=== USER CONTENT ARG ===",
            user_content,
            "",
            "=== MODEL OUTPUT ===",
            completion.text if completion else "",
            "",
            "=== USAGE ===",
            json.dumps(
                redact_persisted_value(completion.usage if completion else None),
                ensure_ascii=False,
                indent=2,
            ),
        ]
    )
    if error is not None:
        lines.extend(["", "=== ERROR ===", safe_exception_detail(error)])
    return (
        redact_sensitive_text(
            "\n".join(lines).rstrip(),
            redact_named_values=False,
            redact_url_fragments=False,
        )
        + "\n"
    )


__all__ = ["format_chat_messages_for_log", "format_model_call_log"]
