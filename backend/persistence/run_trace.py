from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Literal

from backend.persistence.common import utc_now_iso
from backend.persistence.locks import run_lock
from backend.persistence.post_run_transaction_guard import (
    require_post_run_mutation_allowed,
)
from backend.persistence.store_topology import (
    ensure_real_directory_chain,
    require_safe_mutable_file,
)
from core.config_safety import redact_persisted_value


DEFAULT_TRACE_PAGE_LIMIT = 500
MAX_TRACE_PAGE_LIMIT = 2_000
_REVERSE_READ_CHUNK_SIZE = 8 * 1024
_TRACE_CURSOR_VERSION = 1
_COMMIT_TRACE_EVENTS = frozenset(
    {
        "cancel_requested",
        "checkpoint_written",
        "done",
        "error",
        "cancelled",
    }
)
TraceDurability = Literal["buffered", "commit"]
_TRANSACTION_ID_KEY = "operation_transaction_id"
_TRANSACTION_EVENT_ORDINAL_KEY = "operation_transaction_event_ordinal"
_TRANSACTION_PAYLOAD_SHA256_KEY = "operation_transaction_payload_sha256"
_TRANSACTION_PAYLOAD_KEYS = frozenset(
    {
        _TRANSACTION_ID_KEY,
        _TRANSACTION_EVENT_ORDINAL_KEY,
        _TRANSACTION_PAYLOAD_SHA256_KEY,
    }
)


class TraceFormatError(ValueError):
    """Raised when a complete JSONL record is malformed or out of sequence."""


class TraceTransactionConflictError(TraceFormatError):
    """Raised when a journal trace identity contradicts persisted history."""


@dataclass(frozen=True, slots=True)
class TracePage:
    records: list[dict[str, Any]]
    after: int
    limit: int
    next_after: int
    has_more: bool
    next_byte_offset: int


@dataclass(frozen=True, slots=True)
class TraceReadCursor:
    sequence: int
    byte_offset: int


@dataclass(frozen=True, slots=True)
class _TraceTail:
    sequence: int | None
    repaired: bool


@dataclass(frozen=True, slots=True)
class _TraceFragment:
    state: Literal["record", "truncated"]
    record: dict[str, Any] | None = None


_PARTIAL_JSON_LITERALS = frozenset(
    {
        "t",
        "tr",
        "tru",
        "f",
        "fa",
        "fal",
        "fals",
        "n",
        "nu",
        "nul",
    }
)


def _json_error_is_provably_truncated(
    error: json.JSONDecodeError,
    text: str,
) -> bool:
    """Return whether adding bytes at EOF could complete an object prefix."""

    if not text.lstrip().startswith("{"):
        return False
    if error.pos >= len(text):
        return True
    if error.msg.startswith("Unterminated string"):
        return True
    if error.msg.startswith("Invalid \\uXXXX escape") and re.search(
        r"\\u[0-9a-fA-F]{0,3}$",
        text,
    ):
        return True
    suffix = text[error.pos:]
    if error.msg == "Expecting value" and suffix in _PARTIAL_JSON_LITERALS:
        return True
    if error.msg == "Expecting ',' delimiter" and re.fullmatch(
        r"(?:[eE][+-]?\d*|\.\d*)",
        suffix,
    ):
        return True
    return False


def _classify_trace_fragment(
    raw_fragment: bytes,
    *,
    path: Path,
    location: str,
    unterminated_final: bool,
) -> _TraceFragment:
    """Classify one nonblank JSONL fragment without using newline as validity."""

    try:
        text = raw_fragment.decode("utf-8")
    except UnicodeDecodeError as exc:
        if (
            unterminated_final
            and raw_fragment.lstrip().startswith(b"{")
            and exc.reason == "unexpected end of data"
            and exc.end == len(raw_fragment)
        ):
            return _TraceFragment(state="truncated")
        raise TraceFormatError(
            f"Malformed trace record at {path}:{location}."
        ) from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        if unterminated_final and _json_error_is_provably_truncated(exc, text):
            return _TraceFragment(state="truncated")
        raise TraceFormatError(
            f"Malformed trace record at {path}:{location}."
        ) from exc
    if not isinstance(value, dict):
        raise TraceFormatError(
            f"Trace record at {path}:{location} is not a JSON object."
        )
    return _TraceFragment(state="record", record=value)


def _line_start(handle: BinaryIO, content_end: int) -> int:
    cursor = content_end
    while cursor > 0:
        chunk_start = max(0, cursor - _REVERSE_READ_CHUNK_SIZE)
        handle.seek(chunk_start)
        chunk = handle.read(cursor - chunk_start)
        newline_index = chunk.rfind(b"\n")
        if newline_index >= 0:
            return chunk_start + newline_index + 1
        cursor = chunk_start
    return 0


def _preceding_trace_sequence(
    handle: BinaryIO,
    *,
    before: int,
    path: Path,
) -> tuple[bool, int | None]:
    """Return the previous nonblank record's explicit sequence, if any."""

    boundary = before
    while boundary > 0:
        content_end = boundary
        while content_end > 0:
            handle.seek(content_end - 1)
            if handle.read(1) not in {b"\r", b"\n"}:
                break
            content_end -= 1
        if content_end == 0:
            return False, None
        start = _line_start(handle, content_end)
        handle.seek(start)
        raw_line = handle.read(content_end - start)
        if not raw_line.strip():
            boundary = start
            continue
        classified = _classify_trace_fragment(
            raw_line,
            path=path,
            location="preceding-final",
            unterminated_final=False,
        )
        record = classified.record
        if record is None:  # pragma: no cover - preceding records are complete
            raise TraceFormatError(f"Preceding trace record in {path} is unavailable.")
        sequence = record.get("sequence")
        if sequence is None:
            return True, None
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise TraceFormatError(f"Invalid trace sequence {sequence!r} in {path}.")
        return True, sequence
    return False, None


def _trace_tail(path: Path, *, repair_incomplete: bool) -> _TraceTail:
    """Read the final valid record without materializing the trace.

    A process can be interrupted midway through the last append.  Such a final
    fragment has no line terminator and is safe to ignore on reads or trim at a
    startup/mutation boundary.  Malformed records that do have a terminator are
    treated as corruption rather than silently discarded.
    """

    if not path.is_file():
        return _TraceTail(sequence=0, repaired=False)

    mode = "r+b" if repair_incomplete else "rb"
    repaired = False
    with path.open(mode) as handle:
        handle.seek(0, os.SEEK_END)
        boundary = handle.tell()
        while boundary > 0:
            content_end = boundary
            while content_end > 0:
                handle.seek(content_end - 1)
                if handle.read(1) not in {b"\r", b"\n"}:
                    break
                content_end -= 1
            if content_end == 0:
                return _TraceTail(sequence=0, repaired=repaired)

            start = _line_start(handle, content_end)
            handle.seek(start)
            raw_line = handle.read(content_end - start)
            if not raw_line.strip():
                boundary = start
                continue

            classified = _classify_trace_fragment(
                raw_line,
                path=path,
                location="final",
                unterminated_final=content_end == boundary,
            )
            if classified.state == "truncated":
                if not repair_incomplete:
                    boundary = start
                    continue
                handle.seek(start)
                handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())
                repaired = True
                boundary = start
                continue
            record = classified.record
            if record is None:  # pragma: no cover - closed classifier state
                raise TraceFormatError(f"Trace record in {path} is unavailable.")

            sequence = record.get("sequence")
            if sequence is None:
                return _TraceTail(sequence=None, repaired=repaired)
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
                raise TraceFormatError(f"Invalid trace sequence {sequence!r} in {path}.")
            has_predecessor, predecessor_sequence = _preceding_trace_sequence(
                handle,
                before=start,
                path=path,
            )
            if not has_predecessor:
                if sequence != 1:
                    raise TraceFormatError(
                        f"Final trace sequence in {path} is {sequence!r}; expected 1."
                    )
            elif predecessor_sequence is None:
                return _TraceTail(sequence=None, repaired=repaired)
            elif sequence != predecessor_sequence + 1:
                raise TraceFormatError(
                    f"Final trace sequence in {path} is {sequence!r}; "
                    f"expected {predecessor_sequence + 1}."
                )
            return _TraceTail(sequence=sequence, repaired=repaired)

    return _TraceTail(sequence=0, repaired=repaired)


def _iter_trace_records_with_offsets_unlocked(
    path: Path,
    *,
    start_byte_offset: int = 0,
    previous_sequence: int = 0,
) -> Iterator[tuple[dict[str, Any], int]]:
    if not path.is_file():
        return

    file_size = path.stat().st_size
    if (
        isinstance(start_byte_offset, bool)
        or not isinstance(start_byte_offset, int)
        or start_byte_offset < 0
        or start_byte_offset > file_size
    ):
        raise TraceFormatError(f"Invalid trace byte cursor {start_byte_offset!r} for {path}.")
    if (
        isinstance(previous_sequence, bool)
        or not isinstance(previous_sequence, int)
        or previous_sequence < 0
    ):
        raise TraceFormatError(f"Invalid preceding trace sequence {previous_sequence!r}.")

    with path.open("rb") as handle:
        if start_byte_offset:
            handle.seek(start_byte_offset - 1)
            if handle.read(1) != b"\n":
                raise TraceFormatError(
                    f"Trace byte cursor {start_byte_offset} is not a record boundary in {path}."
                )
        handle.seek(start_byte_offset)
        line_number = previous_sequence
        while True:
            raw_line = handle.readline()
            if not raw_line:
                break
            line_number += 1
            if not raw_line.strip():
                continue
            is_unterminated_final = (
                handle.tell() == file_size and not raw_line.endswith(b"\n")
            )
            classified = _classify_trace_fragment(
                raw_line,
                path=path,
                location=str(line_number),
                unterminated_final=is_unterminated_final,
            )
            if classified.state == "truncated":
                break
            record = classified.record
            if record is None:  # pragma: no cover - closed classifier state
                raise TraceFormatError(
                    f"Trace record at {path}:{line_number} is unavailable."
                )

            sequence = record.get("sequence")
            if sequence is None:
                sequence = previous_sequence + 1
                record = {**record, "sequence": sequence}
            if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence != previous_sequence + 1:
                raise TraceFormatError(
                    f"Trace sequence at {path}:{line_number} is {sequence!r}; "
                    f"expected {previous_sequence + 1}."
                )
            previous_sequence = sequence
            yield record, handle.tell()


def _iter_trace_records_unlocked(path: Path) -> Iterator[dict[str, Any]]:
    for record, _next_byte_offset in _iter_trace_records_with_offsets_unlocked(path):
        yield record


def _has_complete_record_after_unlocked(
    path: Path,
    byte_offset: int,
    *,
    previous_sequence: int,
) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        handle.seek(byte_offset)
        while raw_line := handle.readline():
            if not raw_line.strip():
                continue
            if raw_line.endswith(b"\n"):
                return True
            classified = _classify_trace_fragment(
                raw_line,
                path=path,
                location="lookahead",
                unterminated_final=True,
            )
            if classified.state == "truncated":
                return False
            record = classified.record
            if record is None:  # pragma: no cover - closed classifier state
                return False
            sequence = record.get("sequence", previous_sequence + 1)
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence != previous_sequence + 1
            ):
                raise TraceFormatError(
                    f"Trace lookahead sequence in {path} is {sequence!r}; "
                    f"expected {previous_sequence + 1}."
                )
            return True
    return False


def _trace_record_count_unlocked(path: Path) -> int:
    return sum(1 for _record in _iter_trace_records_unlocked(path))


def canonical_trace_payload_bytes(payload: dict[str, Any]) -> bytes:
    safe_payload = redact_persisted_value(payload)
    if not isinstance(safe_payload, dict):  # pragma: no cover - dict input contract
        raise TypeError("Trace payload redaction must preserve its object shape.")
    return json.dumps(
        safe_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def trace_payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_trace_payload_bytes(payload)).hexdigest()


def append_trace_event(
    path: Path,
    *,
    event: str,
    payload: dict[str, Any],
    timestamp_utc: str | None = None,
    durability: TraceDurability | None = None,
    _transaction_id: str | None = None,
) -> dict[str, Any]:
    resolved_durability = (
        "commit" if event in _COMMIT_TRACE_EVENTS else "buffered"
    ) if durability is None else durability
    if resolved_durability not in {"buffered", "commit"}:
        raise ValueError("Trace durability must be 'buffered' or 'commit'.")
    safe_payload = redact_persisted_value(payload)
    if not isinstance(safe_payload, dict):  # pragma: no cover - dict input contract
        raise TypeError("Trace payload redaction must preserve its object shape.")
    with run_lock(path.parent):
        require_post_run_mutation_allowed(
            path.parent,
            transaction_id=_transaction_id,
        )
        ensure_real_directory_chain(path.parent.parent, path.parent)
        require_safe_mutable_file(
            path,
            allow_missing=True,
            label="Run trace",
        )
        tail = _trace_tail(path, repair_incomplete=True)
        last_sequence = tail.sequence
        if last_sequence is None:
            last_sequence = _trace_record_count_unlocked(path)
        record = {
            "sequence": last_sequence + 1,
            "timestamp_utc": timestamp_utc or utc_now_iso(),
            "event": event,
            "payload": safe_payload,
        }
        needs_separator = path.is_file() and path.stat().st_size > 0
        if needs_separator:
            with path.open("rb") as read_handle:
                read_handle.seek(-1, os.SEEK_END)
                needs_separator = read_handle.read(1) not in {b"\r", b"\n"}
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            if needs_separator:
                handle.write("\n")
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            if resolved_durability == "commit":
                os.fsync(handle.fileno())
        return record


def prepare_trace_transaction_boundary(path: Path) -> TraceReadCursor:
    """Repair a crash fragment and return a canonical append boundary."""

    with run_lock(path.parent):
        require_post_run_mutation_allowed(path.parent)
        ensure_real_directory_chain(path.parent.parent, path.parent)
        require_safe_mutable_file(
            path,
            allow_missing=True,
            label="Run trace",
        )
        _trace_tail(path, repair_incomplete=True)
        if not path.is_file():
            return TraceReadCursor(sequence=0, byte_offset=0)

        last_sequence = 0
        last_offset = 0
        for record, record_end_offset in _iter_trace_records_with_offsets_unlocked(
            path
        ):
            last_sequence = int(record["sequence"])
            last_offset = record_end_offset

        physical_size = path.stat().st_size
        if physical_size > last_offset:
            with path.open("rb") as handle:
                handle.seek(last_offset)
                remainder = handle.read()
            if remainder.strip():
                raise TraceFormatError(
                    f"Trace has noncanonical bytes after its final record in {path}."
                )
            with path.open("r+b") as handle:
                handle.seek(last_offset)
                handle.truncate()
                handle.flush()
                os.fsync(handle.fileno())
            physical_size = last_offset

        if physical_size:
            with path.open("rb") as handle:
                handle.seek(-1, os.SEEK_END)
                needs_separator = handle.read(1) != b"\n"
            if needs_separator:
                with path.open("ab") as handle:
                    handle.write(b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                physical_size += 1
        return TraceReadCursor(
            sequence=last_sequence,
            byte_offset=physical_size,
        )


def append_trace_event_once(
    path: Path,
    *,
    transaction_id: str,
    event_ordinal: int,
    event: str,
    payload: dict[str, Any],
    base_cursor: TraceReadCursor,
    durability: TraceDurability = "commit",
) -> dict[str, Any]:
    """Append one journal-owned event, or return its exact durable predecessor."""

    if (
        not transaction_id
        or isinstance(event_ordinal, bool)
        or not isinstance(event_ordinal, int)
        or event_ordinal < 0
    ):
        raise ValueError("Transaction trace identity is invalid.")
    if _TRANSACTION_PAYLOAD_KEYS.intersection(payload):
        raise ValueError("Trace payload uses reserved transaction identity fields.")
    expected_payload_hash = trace_payload_sha256(payload)
    with run_lock(path.parent):
        require_post_run_mutation_allowed(
            path.parent,
            transaction_id=transaction_id,
        )
        matching: dict[str, Any] | None = None
        seen_ordinals: set[int] = set()
        for record, _record_end_offset in _iter_trace_records_with_offsets_unlocked(
            path,
            start_byte_offset=base_cursor.byte_offset,
            previous_sequence=base_cursor.sequence,
        ):
            record_payload = record.get("payload")
            if not isinstance(record_payload, dict):
                raise TraceTransactionConflictError(
                    "Transaction trace payload is not an object."
                )
            persisted_transaction_id = record_payload.get(_TRANSACTION_ID_KEY)
            persisted_ordinal = record_payload.get(
                _TRANSACTION_EVENT_ORDINAL_KEY
            )
            if (
                persisted_transaction_id != transaction_id
                or isinstance(persisted_ordinal, bool)
                or not isinstance(persisted_ordinal, int)
                or persisted_ordinal < 0
                or persisted_ordinal in seen_ordinals
            ):
                raise TraceTransactionConflictError(
                    "Trace history after the transaction base cursor conflicts."
                )
            seen_ordinals.add(persisted_ordinal)
            if persisted_ordinal != event_ordinal:
                continue
            persisted_hash = record_payload.get(
                _TRANSACTION_PAYLOAD_SHA256_KEY
            )
            semantic_payload = {
                key: value
                for key, value in record_payload.items()
                if key not in _TRANSACTION_PAYLOAD_KEYS
            }
            if (
                record.get("event") != event
                or persisted_hash != expected_payload_hash
                or trace_payload_sha256(semantic_payload)
                != expected_payload_hash
            ):
                raise TraceTransactionConflictError(
                    "Persisted transaction trace identity has different content."
                )
            matching = record
        if matching is not None:
            return matching

        return append_trace_event(
            path,
            event=event,
            payload={
                **payload,
                _TRANSACTION_ID_KEY: transaction_id,
                _TRANSACTION_EVENT_ORDINAL_KEY: event_ordinal,
                _TRANSACTION_PAYLOAD_SHA256_KEY: expected_payload_hash,
            },
            durability=durability,
            _transaction_id=transaction_id,
        )


def load_trace_page(
    path: Path,
    *,
    after: int = 0,
    limit: int = DEFAULT_TRACE_PAGE_LIMIT,
    cursor: TraceReadCursor | None = None,
) -> TracePage:
    if isinstance(after, bool) or not isinstance(after, int) or after < 0:
        raise ValueError("Trace cursor 'after' must be a non-negative integer.")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_TRACE_PAGE_LIMIT:
        raise ValueError(f"Trace page limit must be between 1 and {MAX_TRACE_PAGE_LIMIT}.")

    start_byte_offset = 0
    previous_sequence = 0
    if cursor is not None:
        if cursor.sequence != after:
            raise ValueError("Trace byte cursor sequence does not match 'after'.")
        start_byte_offset = cursor.byte_offset
        previous_sequence = cursor.sequence

    with run_lock(path.parent):
        records: list[dict[str, Any]] = []
        has_more = False
        next_byte_offset = start_byte_offset
        for record, record_end_offset in _iter_trace_records_with_offsets_unlocked(
            path,
            start_byte_offset=start_byte_offset,
            previous_sequence=previous_sequence,
        ):
            if record["sequence"] <= after:
                continue
            records.append(record)
            next_byte_offset = record_end_offset
            if len(records) == limit:
                has_more = _has_complete_record_after_unlocked(
                    path,
                    next_byte_offset,
                    previous_sequence=int(record["sequence"]),
                )
                break

    next_after = records[-1]["sequence"] if records else after
    return TracePage(
        records=records,
        after=after,
        limit=limit,
        next_after=next_after,
        has_more=has_more,
        next_byte_offset=next_byte_offset,
    )


def encode_trace_cursor(run_id: str, cursor: TraceReadCursor) -> str:
    payload = {
        "v": _TRACE_CURSOR_VERSION,
        "run_id": str(run_id),
        "sequence": cursor.sequence,
        "byte_offset": cursor.byte_offset,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
    ).decode("ascii")
    return encoded.rstrip("=")


def decode_trace_cursor(value: str, *, run_id: str) -> TraceReadCursor:
    token = str(value or "").strip()
    if not token or len(token) > 512:
        raise ValueError("Invalid trace continuation cursor.")
    try:
        padding = "=" * (-len(token) % 4)
        payload = json.loads(base64.b64decode(token + padding, altchars=b"-_", validate=True))
    except (binascii.Error, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid trace continuation cursor.") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"v", "run_id", "sequence", "byte_offset"}
        or payload.get("v") != _TRACE_CURSOR_VERSION
        or payload.get("run_id") != run_id
    ):
        raise ValueError("Trace continuation cursor does not match this run.")
    sequence = payload.get("sequence")
    byte_offset = payload.get("byte_offset")
    if (
        isinstance(sequence, bool)
        or not isinstance(sequence, int)
        or sequence < 0
        or isinstance(byte_offset, bool)
        or not isinstance(byte_offset, int)
        or byte_offset < 0
    ):
        raise ValueError("Invalid trace continuation cursor.")
    return TraceReadCursor(sequence=sequence, byte_offset=byte_offset)


def load_trace(path: Path) -> list[dict[str, Any]]:
    """Compatibility loader for callers that intentionally need the full trace."""

    with run_lock(path.parent):
        return list(_iter_trace_records_unlocked(path))


def validate_trace(path: Path) -> int:
    """Validate a complete trace incrementally without retaining its records."""

    with run_lock(path.parent):
        return sum(1 for _record in _iter_trace_records_unlocked(path))


def trace_event_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with run_lock(path.parent):
        tail = _trace_tail(path, repair_incomplete=False)
        if tail.sequence is not None:
            return tail.sequence
        return _trace_record_count_unlocked(path)


def repair_incomplete_trace_tail(path: Path) -> bool:
    """Trim one crash-truncated final record at an explicit mutation boundary."""

    with run_lock(path.parent):
        return _trace_tail(path, repair_incomplete=True).repaired


__all__ = [
    "DEFAULT_TRACE_PAGE_LIMIT",
    "MAX_TRACE_PAGE_LIMIT",
    "TraceFormatError",
    "TracePage",
    "TraceReadCursor",
    "TraceTransactionConflictError",
    "TraceDurability",
    "append_trace_event",
    "append_trace_event_once",
    "canonical_trace_payload_bytes",
    "decode_trace_cursor",
    "encode_trace_cursor",
    "load_trace",
    "load_trace_page",
    "prepare_trace_transaction_boundary",
    "repair_incomplete_trace_tail",
    "trace_payload_sha256",
    "trace_event_count",
    "validate_trace",
]
