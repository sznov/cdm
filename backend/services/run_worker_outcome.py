from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from core.config_safety import redact_persisted_value, redact_sensitive_text


WorkerTerminalStatus = Literal["completed", "failed"]


@dataclass(frozen=True, slots=True)
class RunWorkerOutcome:
    """Non-terminal worker result committed only by ``RunCoordinator``."""

    status: WorkerTerminalStatus
    terminal_payload: dict[str, Any]
    result_payload: dict[str, Any] | None = None
    error: str | None = None
    correction_sequence: dict[str, Any] | None = None

    @classmethod
    def completed(cls, result_payload: dict[str, Any]) -> RunWorkerOutcome:
        detached = redact_persisted_value(deepcopy(result_payload))
        if not isinstance(detached, dict):
            raise TypeError("Completed run payload must remain a JSON object.")
        return cls(
            status="completed",
            terminal_payload=deepcopy(detached),
            result_payload=deepcopy(detached),
        )

    @classmethod
    def failed(
        cls,
        error: str,
        *,
        result_payload: dict[str, Any] | None = None,
        correction_sequence: dict[str, Any] | None = None,
    ) -> RunWorkerOutcome:
        safe_error = redact_sensitive_text(error)
        detached_result = redact_persisted_value(deepcopy(result_payload))
        if detached_result is not None and not isinstance(detached_result, dict):
            raise TypeError("Failed run result payload must remain a JSON object.")
        detached_correction = redact_persisted_value(deepcopy(correction_sequence))
        if detached_correction is not None and not isinstance(detached_correction, dict):
            raise TypeError("Correction-sequence payload must remain a JSON object.")
        return cls(
            status="failed",
            terminal_payload={"detail": safe_error},
            result_payload=detached_result,
            error=safe_error,
            correction_sequence=detached_correction,
        )

    def detached_terminal_payload(self) -> dict[str, Any]:
        return deepcopy(self.terminal_payload)

    def detached_result_payload(self) -> dict[str, Any] | None:
        return deepcopy(self.result_payload)

    def detached_correction_sequence(self) -> dict[str, Any] | None:
        return deepcopy(self.correction_sequence)


__all__ = ["RunWorkerOutcome", "WorkerTerminalStatus"]
