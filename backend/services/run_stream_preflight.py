from __future__ import annotations

import asyncio
from pathlib import Path

from backend.api.models import RunRequest
from backend.services.prepared_run import PreparedRun
from backend.services.runtime_run_preparation import prepare_run


async def validated_run_stream_request(
    request: RunRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path | None = None,
    providers_dir: Path | None = None,
) -> PreparedRun:
    """Prepare the complete immutable run before reserving or scheduling it."""

    return await asyncio.to_thread(
        prepare_run,
        request,
        runs_dir=runs_dir,
        sessions_dir=sessions_dir,
        providers_dir=providers_dir,
    )


__all__ = ["validated_run_stream_request"]
