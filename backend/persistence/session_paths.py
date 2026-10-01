from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from core.job_ids import make_job_id
from backend.api.settings import SESSION_RECORD_FILENAME
from backend.persistence.store_topology import (
    StoreTopologyError,
    entry_exists,
    inspect_entry,
    require_real_directory,
)


def make_session_id() -> str:
    return make_job_id().replace("job-", "session-", 1)


def safe_session_dir(session_id: str, *, sessions_dir: Path) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", session_id):
        raise HTTPException(status_code=400, detail="Invalid session id.")
    root = Path(sessions_dir)
    path = root / session_id
    try:
        if entry_exists(root):
            require_real_directory(root, label="Sessions directory")
        entry = inspect_entry(path)
        if entry is not None and (entry.is_reparse or not entry.is_directory):
            raise StoreTopologyError("Session directory topology is unsafe.")
    except StoreTopologyError as exc:
        raise HTTPException(status_code=409, detail="session_store_topology_error") from exc
    return path


def session_record_path(session_id: str, *, sessions_dir: Path) -> Path:
    return safe_session_dir(session_id, sessions_dir=sessions_dir) / SESSION_RECORD_FILENAME


__all__ = [
    "make_session_id",
    "safe_session_dir",
    "session_record_path",
]
