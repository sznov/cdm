from __future__ import annotations

import asyncio
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ActiveRun:
    job_id: str
    task: asyncio.Task[None]
    record_path: Path
    trace_path: Path
    session_id: str | None = None


ACTIVE_RUNS: dict[str, ActiveRun] = {}


def active_run_registry(active_runs: MutableMapping[str, ActiveRun] | None = None) -> MutableMapping[str, ActiveRun]:
    return active_runs if active_runs is not None else ACTIVE_RUNS


def run_is_active(job_id: str, active_runs: MutableMapping[str, ActiveRun] | None = None) -> bool:
    return job_id in active_run_registry(active_runs)


__all__ = ["ACTIVE_RUNS", "ActiveRun", "active_run_registry", "run_is_active"]
