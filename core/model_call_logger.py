from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config_safety import (
    redact_persisted_value,
    redact_sensitive_text,
    safe_exception_detail,
)
from core.model_call_format import format_model_call_log
from core.model_client import ChatMessage, CompletionResult
from core.atomic_io import (
    synchronize_directory,
    synchronized_mkdir,
    synchronized_unlink,
)


def safe_log_slug(value: str) -> str:
    slug = "".join(char if char.isalnum() else "-" for char in value.lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "model-call"


def is_model_call_reservation_name(value: str) -> bool:
    return _global_reservation_index(value) is not None or (
        _legacy_reservation_index(value) is not None
    )


def _positive_padded_index(value: str) -> int | None:
    if (
        len(value) < 4
        or not value.isascii()
        or not value.isdecimal()
    ):
        return None
    index = int(value)
    return index if index > 0 else None


def _global_reservation_index(value: str) -> int | None:
    prefix = "."
    suffix = ".model-call.pending"
    if not value.startswith(prefix) or not value.endswith(suffix):
        return None
    return _positive_padded_index(value[1 : -len(suffix)])


def _legacy_reservation_index(value: str) -> int | None:
    suffix = ".txt.pending"
    if not value.endswith(suffix):
        return None
    identity = value[: -len(suffix)]
    raw_index, separator, slug = identity.partition("_")
    index = _positive_padded_index(raw_index)
    if (
        index is None
        or separator != "_"
        or not slug
        or safe_log_slug(slug) != slug
    ):
        return None
    return index


def _completed_transcript_index(value: str) -> int | None:
    suffix = ".txt"
    if value.startswith(".") or not value.endswith(suffix):
        return None
    identity = value[: -len(suffix)]
    raw_index, separator, slug = identity.partition("_")
    index = _positive_padded_index(raw_index)
    if (
        index is None
        or separator != "_"
        or not slug
        or safe_log_slug(slug) != slug
    ):
        return None
    return index


def model_call_occupied_index(value: str) -> int | None:
    """Return the globally occupied numeric identity for a known artifact."""

    return (
        _global_reservation_index(value)
        or _legacy_reservation_index(value)
        or _completed_transcript_index(value)
    )


@dataclass
class ModelCallLogReservation:
    call_index: int
    kind: str
    final_path: Path | None = None
    pending_path: Path | None = None


@dataclass
class ModelCallLogger:
    job_id: str
    log_dir: Path | None = None
    counter: int = 0
    records: list[dict[str, Any]] = field(default_factory=list)
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def reserve(self, kind: str) -> ModelCallLogReservation:
        """Reserve one immutable sequential transcript identity."""

        with self._lock:
            next_index = self.counter + 1
            if self.log_dir is None:
                self.counter = next_index
                return ModelCallLogReservation(
                    call_index=next_index,
                    kind=kind,
                )

            synchronized_mkdir(self.log_dir, parents=True, exist_ok=True)
            slug = safe_log_slug(kind)
            occupied = {
                index
                for path in self.log_dir.iterdir()
                if (index := model_call_occupied_index(path.name)) is not None
            }
            if occupied:
                next_index = max(next_index, max(occupied) + 1)
            while True:
                filename = f"{next_index:04d}_{slug}.txt"
                final_path = self.log_dir / filename
                pending_path = (
                    self.log_dir
                    / f".{next_index:04d}.model-call.pending"
                )
                try:
                    descriptor = os.open(
                        pending_path,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                        0o600,
                    )
                except FileExistsError:
                    next_index += 1
                    continue
                else:
                    os.close(descriptor)
                    synchronize_directory(self.log_dir)
                    self.counter = next_index
                    return ModelCallLogReservation(
                        call_index=next_index,
                        kind=kind,
                        final_path=final_path,
                        pending_path=pending_path,
                    )

    def write(
        self,
        *,
        kind: str,
        system_prompt: str,
        user_content: str,
        messages: list[ChatMessage] | None,
        completion: CompletionResult | None = None,
        error: BaseException | None = None,
        metadata: dict[str, Any] | None = None,
        reservation: ModelCallLogReservation | None = None,
    ) -> dict[str, Any] | None:
        reservation = reservation or self.reserve(kind)
        if reservation.kind != kind:
            raise ValueError("Model-call reservation kind does not match the transcript.")
        call_index = reservation.call_index
        record: dict[str, Any] = {
            "job_id": self.job_id,
            "call_index": call_index,
            "kind": kind,
            "metadata": redact_persisted_value(metadata or {}),
            "model": (
                redact_sensitive_text(completion.model, redact_named_values=False)
                if completion
                else None
            ),
            "usage": redact_persisted_value(completion.usage) if completion else None,
            "error": safe_exception_detail(error) if error else None,
        }
        if self.log_dir is None:
            with self._lock:
                self.records.append(record)
            return record

        path = reservation.final_path
        pending_path = reservation.pending_path
        if path is None or pending_path is None:
            raise ValueError("Disk-backed model-call reservation is incomplete.")
        text = format_model_call_log(
            job_id=self.job_id,
            call_index=call_index,
            kind=kind,
            system_prompt=system_prompt,
            user_content=user_content,
            messages=messages,
            completion=completion,
            error=error,
            metadata=metadata or {},
        )
        self._publish_reserved(path, pending_path, text)
        record["path"] = str(path)
        with self._lock:
            self.records.append(record)
        return record

    @staticmethod
    def _publish_reserved(path: Path, pending_path: Path, text: str) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        published = False
        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
                newline="",
            ) as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            # A same-directory hard link is an atomic no-replace publication:
            # another completed transcript can never be overwritten.
            os.link(temporary_path, path)
            published = True
            synchronize_directory(path.parent)
        finally:
            try:
                synchronized_unlink(temporary_path, missing_ok=True)
            except OSError:
                pass
        if published:
            try:
                synchronized_unlink(pending_path, missing_ok=True)
            except OSError:
                # The completed transcript is authoritative. Startup safely
                # removes a leftover valid zero-byte reservation.
                pass


__all__ = [
    "is_model_call_reservation_name",
    "model_call_occupied_index",
    "ModelCallLogger",
    "ModelCallLogReservation",
    "safe_log_slug",
]
