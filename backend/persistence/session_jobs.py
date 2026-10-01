from __future__ import annotations

from pathlib import Path

from backend.persistence.session_records import mutate_session_record


def attach_job_to_session(
    session_id: str | None,
    job_id: str,
    *,
    sessions_dir: Path | None,
) -> None:
    """Maintain the rebuildable session-to-run index.

    Callers that treat this index as advisory own their error policy. Keeping
    the mutation itself strict prevents a filesystem or validation failure
    from being mistaken for a successful update.
    """

    if not session_id or sessions_dir is None:
        return

    def attach(record: dict) -> None:
        job_ids = [str(existing) for existing in record.get("job_ids") or [] if str(existing).strip()]
        if job_id not in job_ids:
            job_ids.append(job_id)
        record["job_ids"] = job_ids

    mutate_session_record(session_id, attach, sessions_dir=sessions_dir)

__all__ = ["attach_job_to_session"]
