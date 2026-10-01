from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

from backend.persistence.store_topology import (
    StoreTopologyError,
    entry_exists,
    inspect_entry,
    require_real_directory,
)


def safe_run_dir(job_id: str, *, runs_dir: Path) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", job_id):
        raise HTTPException(status_code=400, detail="Invalid run id.")
    root = Path(runs_dir)
    path = root / job_id
    try:
        if entry_exists(root):
            require_real_directory(root, label="Runs directory")
        entry = inspect_entry(path)
        if entry is not None and (entry.is_reparse or not entry.is_directory):
            raise StoreTopologyError("Run directory topology is unsafe.")
    except StoreTopologyError as exc:
        raise HTTPException(status_code=409, detail="run_store_topology_error") from exc
    return path
