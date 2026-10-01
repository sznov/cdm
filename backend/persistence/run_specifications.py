from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.api.settings import RUN_SPECIFICATION_FILENAME
from harnesses.provenance import text_sha256


class RunSpecificationIntegrityError(RuntimeError):
    """Raised when a run's immutable source specification cannot be verified."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"Recorded run specification failed integrity check: {reason_code}.")


def read_sealed_run_specification(
    run_dir: Path,
    record: dict[str, Any],
) -> str:
    request_payload = record.get("request")
    if not isinstance(request_payload, dict):
        raise RunSpecificationIntegrityError("invalid_specification_reference")
    if request_payload.get("specification_path") != RUN_SPECIFICATION_FILENAME:
        raise RunSpecificationIntegrityError("invalid_specification_reference")

    specification_path = run_dir / RUN_SPECIFICATION_FILENAME
    if not specification_path.is_file():
        raise RunSpecificationIntegrityError("missing_specification")
    try:
        raw_specification = specification_path.read_bytes()
    except OSError as exc:
        raise RunSpecificationIntegrityError("unreadable_specification") from exc
    try:
        specification = raw_specification.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RunSpecificationIntegrityError("invalid_utf8_specification") from exc

    expected_length = request_payload.get("specification_length")
    if (
        isinstance(expected_length, bool)
        or not isinstance(expected_length, int)
        or expected_length != len(specification)
    ):
        raise RunSpecificationIntegrityError("specification_length_mismatch")
    expected_hash = request_payload.get("specification_sha256")
    if not isinstance(expected_hash, str) or expected_hash != text_sha256(specification):
        raise RunSpecificationIntegrityError("specification_hash_mismatch")
    return specification


__all__ = [
    "RunSpecificationIntegrityError",
    "read_sealed_run_specification",
]
