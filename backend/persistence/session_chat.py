from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from backend.persistence.common import utc_now_iso
from backend.persistence.session_records import mutate_session_record, read_session_record


def session_comments_context(session_id: str | None, *, sessions_dir: Path) -> str:
    if not session_id:
        return ""
    try:
        record = read_session_record(session_id, sessions_dir=sessions_dir)
    except HTTPException:
        return ""
    comments = record.get("decision_comments") if isinstance(record.get("decision_comments"), dict) else {}
    chat_messages = record.get("chat_messages") if isinstance(record.get("chat_messages"), list) else []
    parts: list[str] = []
    if comments:
        parts.append("Decision/assumption comments:")
        for key, value in comments.items():
            text = value.get("text") if isinstance(value, dict) else value
            if str(text or "").strip():
                parts.append(f"- {key}: {str(text).strip()}")
    recent = [
        message for message in chat_messages[-8:]
        if (
            isinstance(message, dict)
            and str(message.get("content") or "").strip()
            and str(message.get("kind") or "") not in {"correction_model_output"}
        )
    ]
    if recent:
        parts.append("Recent session chat:")
        for message in recent:
            role = str(message.get("role") or "message")
            content = str(message.get("content") or "").strip()
            parts.append(f"- {role}: {content}")
    return "\n".join(parts).strip()


def append_session_chat_message(
    session_id: str | None,
    role: str,
    content: str,
    *,
    kind: str = "message",
    sessions_dir: Path,
) -> None:
    if not session_id or not str(content or "").strip():
        return

    def append_message(record: dict) -> None:
        messages = record.get("chat_messages") if isinstance(record.get("chat_messages"), list) else []
        item = {
            "id": f"msg-{len(messages) + 1:04d}",
            "role": role,
            "kind": kind,
            "content": content.strip(),
            "created_at_utc": utc_now_iso(),
        }
        messages.append(item)
        record["chat_messages"] = messages

    try:
        mutate_session_record(session_id, append_message, sessions_dir=sessions_dir)
    except HTTPException:
        return


__all__ = [
    "append_session_chat_message",
    "session_comments_context",
]
