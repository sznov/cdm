from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def make_job_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"job-{timestamp}-{uuid4().hex[:8]}"


__all__ = ["make_job_id"]
