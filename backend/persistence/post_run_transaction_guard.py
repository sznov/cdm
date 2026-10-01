from __future__ import annotations

import json
from pathlib import Path

from backend.persistence.store_topology import inspect_entry


POST_RUN_TRANSACTION_FILENAME = "post-run-transaction.json"


class PostRunTransactionPendingError(RuntimeError):
    """Raised when ordinary mutation would cross a pending transaction."""


def post_run_transaction_path(run_dir: Path) -> Path:
    return Path(run_dir) / POST_RUN_TRANSACTION_FILENAME


def pending_post_run_transaction_id(run_dir: Path) -> str | None:
    path = post_run_transaction_path(run_dir)
    entry = inspect_entry(path)
    if entry is None:
        return None
    if (
        entry.is_reparse
        or not entry.is_regular_file
        or int(getattr(entry.stat_result, "st_nlink", 1)) != 1
    ):
        raise PostRunTransactionPendingError(
            "Pending post-run transaction metadata is unsafe."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PostRunTransactionPendingError(
            "Pending post-run transaction metadata is invalid."
        ) from exc
    transaction_id = (
        str(payload.get("transaction_id") or "").strip()
        if isinstance(payload, dict)
        else ""
    )
    if not transaction_id:
        raise PostRunTransactionPendingError(
            "Pending post-run transaction identity is invalid."
        )
    return transaction_id


def require_post_run_mutation_allowed(
    run_dir: Path,
    *,
    transaction_id: str | None = None,
) -> None:
    pending_id = pending_post_run_transaction_id(run_dir)
    if pending_id is None or (
        transaction_id is not None and transaction_id == pending_id
    ):
        return
    raise PostRunTransactionPendingError(
        "A post-run transaction is pending for this run."
    )


__all__ = [
    "POST_RUN_TRANSACTION_FILENAME",
    "PostRunTransactionPendingError",
    "pending_post_run_transaction_id",
    "post_run_transaction_path",
    "require_post_run_mutation_allowed",
]
