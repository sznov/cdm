from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from core.artifact_versions import add_session_record_version
from backend.persistence.common import utc_now_iso, write_json_file
from backend.persistence.locks import session_lock
from backend.persistence.session_paths import session_record_path
from backend.persistence.session_record_integrity import (
    SessionRecordIntegrityError,
    read_canonical_session_record,
    validate_canonical_session_record,
    validate_canonical_session_record_context,
)


def read_session_record(session_id: str, *, sessions_dir: Path) -> dict[str, Any]:
    path = session_record_path(session_id, sessions_dir=sessions_dir)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        return read_canonical_session_record(path, sessions_dir=sessions_dir)
    except SessionRecordIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="session_record_integrity_error",
        ) from exc


def update_session_record(session_id: str, *, sessions_dir: Path, **changes: Any) -> dict[str, Any]:
    def apply_changes(record: dict[str, Any]) -> None:
        record.update(changes)

    return mutate_session_record(session_id, apply_changes, sessions_dir=sessions_dir)


def mutate_session_record(
    session_id: str,
    mutation: Callable[[dict[str, Any]], None],
    *,
    sessions_dir: Path,
) -> dict[str, Any]:
    path = session_record_path(session_id, sessions_dir=sessions_dir)
    with session_lock(path):
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Session not found.")
        try:
            record = read_canonical_session_record(path, sessions_dir=sessions_dir)
        except SessionRecordIntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="session_record_integrity_error",
            ) from exc
        mutation(record)
        record.pop("status", None)
        record.pop("active_job_id", None)
        record["updated_at_utc"] = utc_now_iso()
        record = add_session_record_version(record)
        record = validate_canonical_session_record(record)
        validate_canonical_session_record_context(
            record,
            record_path=path,
            sessions_dir=sessions_dir,
        )
        write_json_file(path, record)
        return record


def repair_session_job_index(
    session_id: str,
    job_ids: list[str],
    *,
    sessions_dir: Path,
) -> bool:
    """Rebuild the advisory run index without changing user-facing recency."""

    path = session_record_path(session_id, sessions_dir=sessions_dir)
    with session_lock(path):
        record = read_canonical_session_record(path, sessions_dir=sessions_dir)
        if record.get("job_ids") == job_ids:
            return False
        record["job_ids"] = list(job_ids)
        record = validate_canonical_session_record(record)
        validate_canonical_session_record_context(
            record,
            record_path=path,
            sessions_dir=sessions_dir,
        )
        write_json_file(path, record)
        return True


def generated_session_title(specification: str, model: str) -> str:
    words = re.findall(r"[^\W_]+", specification, flags=re.UNICODE)
    prefix = " ".join(words[:5]).strip() or "Research session"
    if len(prefix) > 54:
        prefix = prefix[:54].rstrip()
    return f"{prefix} · {model}".strip()


__all__ = [
    "generated_session_title",
    "mutate_session_record",
    "read_session_record",
    "repair_session_job_index",
    "update_session_record",
]
