from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from backend.services.run_operation_registry import (
    RunOperationHandle,
    RunOperationKind,
    RunOperationRegistry,
    claim_run_operation,
)
from backend.services.run_queries import read_run_record


def recorded_run_session_id(job_id: str, *, runs_dir: Path) -> str | None:
    """Read the trusted session identity before claiming operation ownership."""

    _run_dir, record = read_run_record(job_id, runs_dir=runs_dir)
    return str(record.get("session_id") or "").strip() or None


@asynccontextmanager
async def claim_recorded_run_operation(
    job_id: str,
    kind: RunOperationKind,
    *,
    runs_dir: Path,
    registry: RunOperationRegistry,
) -> AsyncIterator[RunOperationHandle]:
    session_id = recorded_run_session_id(job_id, runs_dir=runs_dir)
    async with claim_run_operation(
        job_id,
        kind,
        registry=registry,
        session_id=session_id,
    ) as handle:
        yield handle


__all__ = ["claim_recorded_run_operation", "recorded_run_session_id"]
