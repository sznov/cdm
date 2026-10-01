from __future__ import annotations


RUN_STATUS_CREATED = "created"
RUN_STATUS_QUEUED = "queued"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_CANCELLING = "cancelling"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_CANCELLED = "cancelled"
RUN_STATUS_INTERRUPTED = "interrupted"

ACTIVE_RUN_STATUSES = frozenset({RUN_STATUS_QUEUED, RUN_STATUS_RUNNING, RUN_STATUS_CANCELLING})
TERMINAL_RUN_STATUSES = frozenset(
    {RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED, RUN_STATUS_INTERRUPTED}
)
TERMINAL_RUN_STATUS_ALIASES = frozenset({"done", "error", "canceled"})


def normalize_status(status: str | None, default: str = "") -> str:
    return str(status or default).strip().lower()


def run_status_is_active(status: str | None) -> bool:
    return normalize_status(status) in ACTIVE_RUN_STATUSES


def run_status_is_terminal(status: str | None) -> bool:
    return normalize_status(status) in TERMINAL_RUN_STATUSES | TERMINAL_RUN_STATUS_ALIASES


def terminal_run_status_kind(status: str | None) -> str:
    normalized = normalize_status(status)
    if normalized in {RUN_STATUS_FAILED, "error"}:
        return "error"
    if normalized in {RUN_STATUS_CANCELLED, "canceled", RUN_STATUS_INTERRUPTED}:
        return "cancelled"
    if normalized in {RUN_STATUS_COMPLETED, "done"}:
        return "done"
    return ""


__all__ = [
    "ACTIVE_RUN_STATUSES",
    "RUN_STATUS_CANCELLED",
    "RUN_STATUS_CANCELLING",
    "RUN_STATUS_COMPLETED",
    "RUN_STATUS_CREATED",
    "RUN_STATUS_FAILED",
    "RUN_STATUS_INTERRUPTED",
    "RUN_STATUS_QUEUED",
    "RUN_STATUS_RUNNING",
    "TERMINAL_RUN_STATUSES",
    "TERMINAL_RUN_STATUS_ALIASES",
    "normalize_status",
    "run_status_is_active",
    "run_status_is_terminal",
    "terminal_run_status_kind",
]
