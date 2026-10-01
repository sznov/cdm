from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


RUN_EVENT_SCHEMA_VERSION = 2
TERMINAL_RUN_EVENT_TYPES = frozenset({"done", "error", "cancelled"})


class RunEventEnvelope(BaseModel):
    """The stable event shape exposed by reconnectable run observation.

    Trace JSONL remains intentionally inspectable and compact.  This model is
    the typed transport boundary used both for newly appended records and for
    records reconstructed during replay.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[2] = RUN_EVENT_SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    session_id: str | None = None
    sequence: int = Field(ge=1)
    type: str = Field(min_length=1)
    timestamp_utc: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_trace_record(
        cls,
        *,
        run_id: str,
        session_id: str | None,
        record: dict[str, Any],
    ) -> RunEventEnvelope:
        event_type = record.get("type") or record.get("event")
        return cls.model_validate(
            {
                "schema_version": RUN_EVENT_SCHEMA_VERSION,
                "run_id": run_id,
                "session_id": session_id,
                "sequence": record.get("sequence"),
                "type": event_type,
                "timestamp_utc": record.get("timestamp_utc"),
                "payload": record.get("payload") if isinstance(record.get("payload"), dict) else {},
            }
        )


__all__ = [
    "RUN_EVENT_SCHEMA_VERSION",
    "TERMINAL_RUN_EVENT_TYPES",
    "RunEventEnvelope",
]
