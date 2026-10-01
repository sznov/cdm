from __future__ import annotations

import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.api.settings import (
    RUN_RECORD_FILENAME,
    RUN_TRACE_FILENAME,
    SESSION_RECORD_FILENAME,
)
from backend.persistence.common import write_json_file
from backend.persistence.locks import run_lock, session_lock
from backend.persistence.post_run_transaction_guard import (
    POST_RUN_TRANSACTION_FILENAME,
    PostRunTransactionPendingError,
    post_run_transaction_path,
)
from backend.persistence.run_path_references import (
    RunPathReferenceError,
    validate_relative_reference,
)
from backend.persistence.run_record_integrity import (
    validate_canonical_run_record,
    validate_canonical_run_record_context,
)
from backend.persistence.run_trace import (
    TraceDurability,
    TraceFormatError,
    TraceReadCursor,
    TraceTransactionConflictError,
    append_trace_event_once,
    canonical_trace_payload_bytes,
    prepare_trace_transaction_boundary,
    trace_payload_sha256,
)
from backend.persistence.session_paths import session_record_path
from backend.persistence.session_record_integrity import (
    SessionRecordIntegrityError,
    read_canonical_session_record,
    validate_canonical_session_record,
    validate_canonical_session_record_context,
)
from backend.persistence.store_topology import (
    StoreTopologyError,
    ensure_real_directory_chain,
    inspect_entry,
    iter_directory_entries,
    remove_verified_tree,
    require_real_directory,
    require_safe_mutable_file,
)
from core.atomic_io import (
    atomic_write_bytes,
    synchronize_directory,
    synchronized_mkdir,
    synchronized_unlink,
)
from core.artifact_versions import normalize_result_payload


POST_RUN_TRANSACTION_ARTIFACT_KIND = "post_run_transaction"
POST_RUN_TRANSACTION_SCHEMA_VERSION = 1
POST_RUN_TRANSACTION_PROTOCOL_VERSION = 1
POST_RUN_TRANSACTION_STAGING_DIRECTORY = "transactions"
POST_RUN_RESULT_TRANSACTION_FIELD = "post_run_transaction"

PostRunTransactionState = Literal[
    "prepared",
    "artifacts_written",
    "result_committed",
    "run_projection_written",
    "session_written",
    "trace_committed",
    "complete",
]
PostRunTargetPhase = Literal[
    "artifact",
    "result",
    "run_projection",
    "session",
]
PostRunTargetScope = Literal["run", "session"]

_STATE_ORDER: tuple[PostRunTransactionState, ...] = (
    "prepared",
    "artifacts_written",
    "result_committed",
    "run_projection_written",
    "session_written",
    "trace_committed",
    "complete",
)
_PHASE_TRANSITIONS: tuple[
    tuple[PostRunTargetPhase, PostRunTransactionState],
    ...,
] = (
    ("artifact", "artifacts_written"),
    ("result", "result_committed"),
    ("run_projection", "run_projection_written"),
    ("session", "session_written"),
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_SHA256 = r"^[0-9a-f]{64}$"


class PostRunTransactionError(RuntimeError):
    """Base error for strict post-run transaction processing."""


class PostRunTransactionIntegrityError(PostRunTransactionError):
    """Raised when a journal, staged payload, or destination is invalid."""


class PostRunTransactionConflictError(PostRunTransactionIntegrityError):
    """Raised when current bytes match neither recorded base nor target state."""


class PostRunTransactionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_record_sha256: str = Field(pattern=_SHA256)
    result_sha256: str | None = Field(default=None, pattern=_SHA256)
    session_record_sha256: str | None = Field(default=None, pattern=_SHA256)
    trace_sequence: int = Field(ge=0)
    trace_byte_offset: int = Field(ge=0)


class PostRunTransactionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int = Field(ge=0)
    phase: PostRunTargetPhase
    scope: PostRunTargetScope
    destination: str = Field(min_length=1)
    staged_path: str = Field(min_length=1)
    base_sha256: str | None = Field(default=None, pattern=_SHA256)
    target_sha256: str = Field(pattern=_SHA256)


class PostRunTransactionTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ordinal: int = Field(ge=0)
    event: str = Field(min_length=1)
    payload_path: str = Field(min_length=1)
    payload_sha256: str = Field(pattern=_SHA256)
    durability: TraceDurability = "commit"


class PostRunTransactionJournal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_kind: Literal["post_run_transaction"]
    schema_version: Literal[1]
    protocol_version: Literal[1]
    transaction_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    operation_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    operation_type: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    run_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    session_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    chat_message_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )
    created_at_utc: str = Field(min_length=1)
    state: PostRunTransactionState
    base: PostRunTransactionBase
    targets: list[PostRunTransactionTarget]
    trace_events: list[PostRunTransactionTraceEvent]

    @model_validator(mode="after")
    def require_closed_transaction_shape(self) -> PostRunTransactionJournal:
        target_ordinals = [target.ordinal for target in self.targets]
        if target_ordinals != list(range(len(self.targets))):
            raise ValueError("transaction target ordinals must be contiguous")
        destinations = [
            (target.scope, target.destination)
            for target in self.targets
        ]
        if len(set(destinations)) != len(destinations):
            raise ValueError("transaction target destinations must be unique")
        result_targets = [
            target
            for target in self.targets
            if target.phase == "result"
        ]
        if (
            len(result_targets) != 1
            or result_targets[0].scope != "run"
            or result_targets[0].destination != "result.json"
        ):
            raise ValueError(
                "a transaction requires exactly one run-local result commit"
            )
        for target in self.targets:
            validate_relative_reference(target.destination)
            validate_relative_reference(target.staged_path)
            expected_prefix = (
                f"{POST_RUN_TRANSACTION_STAGING_DIRECTORY}/"
                f"{self.transaction_id}/"
            )
            if not target.staged_path.startswith(expected_prefix):
                raise ValueError("transaction target stage path is inconsistent")
            if target.scope == "session":
                if (
                    not self.session_id
                    or target.phase != "session"
                    or target.destination != SESSION_RECORD_FILENAME
                ):
                    raise ValueError("session targets require one canonical session")
            elif target.phase == "session":
                raise ValueError("session phase targets must use session scope")
            if target.scope == "run":
                if target.destination in {
                    POST_RUN_TRANSACTION_FILENAME,
                    RUN_TRACE_FILENAME,
                    "specification.txt",
                } or (
                    target.destination.split("/", 1)[0]
                    == POST_RUN_TRANSACTION_STAGING_DIRECTORY
                ):
                    raise ValueError(
                        "transaction cannot replace its own authority"
                    )
                if (
                    target.destination == RUN_RECORD_FILENAME
                    and target.phase != "run_projection"
                ):
                    raise ValueError(
                        "run record targets belong to the projection phase"
                    )

        event_ordinals = [event.ordinal for event in self.trace_events]
        if event_ordinals != list(range(len(self.trace_events))):
            raise ValueError("transaction trace ordinals must be contiguous")
        for event in self.trace_events:
            validate_relative_reference(event.payload_path)
            expected_prefix = (
                f"{POST_RUN_TRANSACTION_STAGING_DIRECTORY}/"
                f"{self.transaction_id}/"
            )
            if not event.payload_path.startswith(expected_prefix):
                raise ValueError("transaction trace stage path is inconsistent")
            if event.durability != "commit":
                raise ValueError(
                    "journal-owned trace events require commit durability"
                )
        return self


@dataclass(frozen=True, slots=True)
class PostRunTargetPayload:
    phase: PostRunTargetPhase
    scope: PostRunTargetScope
    destination: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class PostRunTraceEventPayload:
    event: str
    payload: dict[str, Any]
    durability: TraceDurability = "commit"


@dataclass(frozen=True, slots=True)
class PostRunTransactionResult:
    transaction_id: str
    trace_records: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class PostRunTransactionRecoveryIssue:
    run_id: str
    reason_code: str


def post_run_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def post_run_payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_exact_bytes(path: Path, *, allow_missing: bool) -> bytes | None:
    entry = inspect_entry(path)
    if entry is None:
        if allow_missing:
            return None
        raise PostRunTransactionIntegrityError(
            f"Required transaction file is missing: {path.name}."
        )
    if (
        entry.is_reparse
        or not entry.is_regular_file
        or int(getattr(entry.stat_result, "st_nlink", 1)) != 1
    ):
        raise PostRunTransactionIntegrityError(
            f"Transaction file is unsafe: {path.name}."
        )
    try:
        return path.read_bytes()
    except OSError as exc:
        raise PostRunTransactionIntegrityError(
            f"Transaction file could not be read: {path.name}."
        ) from exc


def _file_sha256(path: Path, *, allow_missing: bool = True) -> str | None:
    payload = _read_exact_bytes(path, allow_missing=allow_missing)
    return post_run_payload_sha256(payload) if payload is not None else None


def _canonical_journal_bytes(journal: PostRunTransactionJournal) -> bytes:
    return post_run_json_bytes(journal.model_dump(mode="json"))


def read_post_run_transaction_journal(
    run_dir: Path,
) -> PostRunTransactionJournal:
    path = post_run_transaction_path(run_dir)
    payload = _read_exact_bytes(path, allow_missing=False)
    if payload is None:  # pragma: no cover - required read contract
        raise PostRunTransactionIntegrityError("Transaction journal is missing.")
    try:
        decoded = json.loads(payload.decode("utf-8"))
        journal = PostRunTransactionJournal.model_validate(decoded)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValidationError,
        RunPathReferenceError,
    ) as exc:
        raise PostRunTransactionIntegrityError(
            "Post-run transaction journal is invalid."
        ) from exc
    if _canonical_journal_bytes(journal) != payload:
        raise PostRunTransactionIntegrityError(
            "Post-run transaction journal is not canonically encoded."
        )
    if journal.run_id != Path(run_dir).name:
        raise PostRunTransactionIntegrityError(
            "Post-run transaction run identity is inconsistent."
        )
    return journal


def _transaction_directory(
    run_dir: Path,
    transaction_id: str,
) -> Path:
    return (
        Path(run_dir)
        / POST_RUN_TRANSACTION_STAGING_DIRECTORY
        / transaction_id
    )


def _staged_path(run_dir: Path, reference: str) -> Path:
    validate_relative_reference(reference)
    return Path(run_dir).joinpath(*reference.split("/"))


def _target_destination(
    run_dir: Path,
    target: PostRunTransactionTarget,
    *,
    session_record: Path | None,
) -> Path:
    validate_relative_reference(target.destination)
    if target.scope == "run":
        return Path(run_dir).joinpath(*target.destination.split("/"))
    if session_record is None:
        raise PostRunTransactionIntegrityError(
            "Transaction session target has no session authority."
        )
    if target.destination != SESSION_RECORD_FILENAME:
        raise PostRunTransactionIntegrityError(
            "Transaction session target is not canonical."
        )
    return session_record


def _ensure_target_topology(
    run_dir: Path,
    *,
    scope: PostRunTargetScope,
    destination: Path,
) -> None:
    root = Path(run_dir) if scope == "run" else destination.parent
    ensure_real_directory_chain(root, destination.parent)
    require_safe_mutable_file(
        destination,
        allow_missing=True,
        label="Post-run transaction destination",
    )


@contextmanager
def _transaction_locks(
    run_dir: Path,
    *,
    session_record: Path | None,
) -> Iterator[None]:
    with run_lock(run_dir):
        if session_record is None:
            yield
        else:
            with session_lock(session_record):
                yield


def _result_target_metadata(
    payload: bytes,
    *,
    transaction_id: str,
    operation_id: str,
    operation_type: str,
) -> None:
    try:
        result = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PostRunTransactionIntegrityError(
            "Transaction result target is not valid UTF-8 JSON."
        ) from exc
    metadata = (
        result.get(POST_RUN_RESULT_TRANSACTION_FIELD)
        if isinstance(result, dict)
        else None
    )
    expected_identity = {
        "transaction_id": transaction_id,
        "operation_id": operation_id,
        "operation_type": operation_type,
    }
    if not isinstance(metadata, dict) or any(
        metadata.get(key) != value
        for key, value in expected_identity.items()
    ):
        raise PostRunTransactionIntegrityError(
            "Transaction result target lacks its exact commit identity."
        )
    try:
        normalize_result_payload(result)
    except (TypeError, ValueError) as exc:
        raise PostRunTransactionIntegrityError(
            "Transaction result target has invalid artifact metadata."
        ) from exc


def _validate_structured_target(
    *,
    run_dir: Path,
    sessions_dir: Path,
    session_record: Path | None,
    target: PostRunTransactionTarget,
    payload: bytes,
    transaction_id: str,
    operation_id: str,
    operation_type: str,
    chat_message_id: str | None,
) -> None:
    if target.destination not in {
        "result.json",
        RUN_RECORD_FILENAME,
        SESSION_RECORD_FILENAME,
    }:
        return
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PostRunTransactionIntegrityError(
            "Structured transaction target is not valid UTF-8 JSON."
        ) from exc
    if target.destination == "result.json":
        _result_target_metadata(
            payload,
            transaction_id=transaction_id,
            operation_id=operation_id,
            operation_type=operation_type,
        )
        return
    if target.destination == RUN_RECORD_FILENAME:
        record = validate_canonical_run_record(value)
        validate_canonical_run_record_context(
            record,
            record_path=Path(run_dir) / RUN_RECORD_FILENAME,
            runs_dir=Path(run_dir).parent,
        )
        return
    if session_record is None:
        raise PostRunTransactionIntegrityError(
            "Session transaction target has no session record."
        )
    record = validate_canonical_session_record(value)
    validate_canonical_session_record_context(
        record,
        record_path=session_record,
        sessions_dir=sessions_dir,
    )
    messages = (
        record.get("chat_messages")
        if isinstance(record.get("chat_messages"), list)
        else []
    )
    matches = [
        message
        for message in messages
        if isinstance(message, dict)
        and message.get("id") == chat_message_id
        and message.get("post_run_transaction_id") == transaction_id
        and message.get("post_run_run_id") == Path(run_dir).name
    ]
    if not chat_message_id or len(matches) != 1:
        raise PostRunTransactionIntegrityError(
            "Session target lacks its stable transaction-tagged chat message."
        )


def _write_staged_payload(path: Path, payload: bytes) -> str:
    atomic_write_bytes(path, payload)
    persisted = _read_exact_bytes(path, allow_missing=False)
    if persisted != payload:
        raise PostRunTransactionIntegrityError(
            "Staged transaction payload changed during publication."
        )
    return post_run_payload_sha256(payload)


def _write_journal(
    run_dir: Path,
    journal: PostRunTransactionJournal,
) -> None:
    atomic_write_bytes(
        post_run_transaction_path(run_dir),
        _canonical_journal_bytes(journal),
    )


def _transition_journal(
    run_dir: Path,
    journal: PostRunTransactionJournal,
    state: PostRunTransactionState,
) -> PostRunTransactionJournal:
    current_index = _STATE_ORDER.index(journal.state)
    next_index = _STATE_ORDER.index(state)
    if next_index < current_index or next_index > current_index + 1:
        raise PostRunTransactionIntegrityError(
            "Post-run transaction state transition is invalid."
        )
    if next_index == current_index:
        return journal
    updated = journal.model_copy(update={"state": state})
    updated = PostRunTransactionJournal.model_validate(
        updated.model_dump(mode="json")
    )
    _write_journal(run_dir, updated)
    return updated


def _base_authority_hashes(
    run_dir: Path,
    *,
    session_record: Path | None,
    trace_cursor: TraceReadCursor,
) -> PostRunTransactionBase:
    return PostRunTransactionBase(
        run_record_sha256=_file_sha256(
            Path(run_dir) / RUN_RECORD_FILENAME,
            allow_missing=False,
        ),
        result_sha256=_file_sha256(Path(run_dir) / "result.json"),
        session_record_sha256=(
            _file_sha256(session_record, allow_missing=False)
            if session_record is not None
            else None
        ),
        trace_sequence=trace_cursor.sequence,
        trace_byte_offset=trace_cursor.byte_offset,
    )


def prepare_post_run_transaction(
    *,
    run_dir: Path,
    sessions_dir: Path,
    transaction_id: str,
    operation_id: str,
    operation_type: str,
    created_at_utc: str,
    targets: list[PostRunTargetPayload],
    trace_events: list[PostRunTraceEventPayload],
    session_id: str | None = None,
    chat_message_id: str | None = None,
) -> PostRunTransactionJournal:
    """Stage and publish one strict transaction intent under all record locks."""

    if not all(
        _SAFE_ID.fullmatch(value)
        for value in (transaction_id, operation_id, operation_type)
    ):
        raise ValueError("Post-run transaction identity is invalid.")
    if session_id is not None and not _SAFE_ID.fullmatch(session_id):
        raise ValueError("Post-run transaction session identity is invalid.")
    session_record = (
        session_record_path(session_id, sessions_dir=sessions_dir)
        if session_id
        else None
    )
    with _transaction_locks(run_dir, session_record=session_record):
        require_real_directory(run_dir, label="Run directory")
        if inspect_entry(post_run_transaction_path(run_dir)) is not None:
            raise PostRunTransactionPendingError(
                "A post-run transaction is already pending for this run."
            )
        trace_cursor = prepare_trace_transaction_boundary(
            Path(run_dir) / RUN_TRACE_FILENAME
        )
        base = _base_authority_hashes(
            run_dir,
            session_record=session_record,
            trace_cursor=trace_cursor,
        )

        transactions_root = (
            Path(run_dir) / POST_RUN_TRANSACTION_STAGING_DIRECTORY
        )
        ensure_real_directory_chain(Path(run_dir), transactions_root)
        transaction_dir = _transaction_directory(run_dir, transaction_id)
        try:
            synchronized_mkdir(transaction_dir, exist_ok=False)
        except FileExistsError as exc:
            raise PostRunTransactionPendingError(
                "Post-run transaction staging identity already exists."
            ) from exc

        journal_targets: list[PostRunTransactionTarget] = []
        journal_events: list[PostRunTransactionTraceEvent] = []
        try:
            seen_destinations: set[tuple[str, str]] = set()
            for ordinal, target in enumerate(targets):
                validate_relative_reference(target.destination)
                destination_key = (target.scope, target.destination)
                if destination_key in seen_destinations:
                    raise PostRunTransactionIntegrityError(
                        "Post-run transaction target is duplicated."
                    )
                seen_destinations.add(destination_key)
                staged_reference = (
                    f"{POST_RUN_TRANSACTION_STAGING_DIRECTORY}/"
                    f"{transaction_id}/target-{ordinal:04d}.bin"
                )
                target_hash = _write_staged_payload(
                    _staged_path(run_dir, staged_reference),
                    bytes(target.payload),
                )
                provisional = PostRunTransactionTarget(
                    ordinal=ordinal,
                    phase=target.phase,
                    scope=target.scope,
                    destination=target.destination,
                    staged_path=staged_reference,
                    base_sha256=None,
                    target_sha256=target_hash,
                )
                destination = _target_destination(
                    run_dir,
                    provisional,
                    session_record=session_record,
                )
                _ensure_target_topology(
                    run_dir,
                    scope=provisional.scope,
                    destination=destination,
                )
                journal_targets.append(
                    provisional.model_copy(
                        update={
                            "base_sha256": _file_sha256(destination),
                        }
                    )
                )

            result_target = next(
                (
                    target
                    for target in journal_targets
                    if target.phase == "result"
                ),
                None,
            )
            if result_target is None:
                raise PostRunTransactionIntegrityError(
                    "Post-run transaction has no result commit target."
                )
            result_payload = _read_exact_bytes(
                _staged_path(run_dir, result_target.staged_path),
                allow_missing=False,
            )
            if result_payload is None:  # pragma: no cover - required stage
                raise PostRunTransactionIntegrityError(
                    "Post-run result target is missing."
                )
            for target in journal_targets:
                target_payload = _read_exact_bytes(
                    _staged_path(run_dir, target.staged_path),
                    allow_missing=False,
                )
                if target_payload is None:  # pragma: no cover - required stage
                    raise PostRunTransactionIntegrityError(
                        "Structured transaction target is missing."
                    )
                _validate_structured_target(
                    run_dir=run_dir,
                    sessions_dir=sessions_dir,
                    session_record=session_record,
                    target=target,
                    payload=target_payload,
                    transaction_id=transaction_id,
                    operation_id=operation_id,
                    operation_type=operation_type,
                    chat_message_id=chat_message_id,
                )

            for ordinal, event in enumerate(trace_events):
                payload_bytes = canonical_trace_payload_bytes(event.payload)
                staged_reference = (
                    f"{POST_RUN_TRANSACTION_STAGING_DIRECTORY}/"
                    f"{transaction_id}/trace-{ordinal:04d}.json"
                )
                payload_hash = _write_staged_payload(
                    _staged_path(run_dir, staged_reference),
                    payload_bytes,
                )
                if payload_hash != trace_payload_sha256(event.payload):
                    raise PostRunTransactionIntegrityError(
                        "Staged trace payload hash is inconsistent."
                    )
                journal_events.append(
                    PostRunTransactionTraceEvent(
                        ordinal=ordinal,
                        event=event.event,
                        payload_path=staged_reference,
                        payload_sha256=payload_hash,
                        durability=event.durability,
                    )
                )

            journal = PostRunTransactionJournal(
                artifact_kind=POST_RUN_TRANSACTION_ARTIFACT_KIND,
                schema_version=POST_RUN_TRANSACTION_SCHEMA_VERSION,
                protocol_version=POST_RUN_TRANSACTION_PROTOCOL_VERSION,
                transaction_id=transaction_id,
                operation_id=operation_id,
                operation_type=operation_type,
                run_id=Path(run_dir).name,
                session_id=session_id,
                chat_message_id=chat_message_id,
                created_at_utc=created_at_utc,
                state="prepared",
                base=base,
                targets=journal_targets,
                trace_events=journal_events,
            )
            _write_journal(run_dir, journal)
            return journal
        except BaseException:
            if not post_run_transaction_path(run_dir).exists():
                try:
                    remove_verified_tree(transaction_dir)
                except OSError:
                    pass
            raise


def _verify_base_authorities(
    run_dir: Path,
    journal: PostRunTransactionJournal,
    *,
    session_record: Path | None,
) -> None:
    authority_targets = {
        ("run", RUN_RECORD_FILENAME): journal.base.run_record_sha256,
        ("run", "result.json"): journal.base.result_sha256,
    }
    if session_record is not None:
        authority_targets[("session", SESSION_RECORD_FILENAME)] = (
            journal.base.session_record_sha256
        )
    targets_by_destination = {
        (target.scope, target.destination): target
        for target in journal.targets
    }
    for identity, expected_base in authority_targets.items():
        target = targets_by_destination.get(identity)
        if target is not None:
            if target.base_sha256 != expected_base:
                raise PostRunTransactionIntegrityError(
                    "Transaction base authority differs from target precondition."
                )
            continue
        scope, destination = identity
        path = (
            Path(run_dir) / destination
            if scope == "run"
            else session_record
        )
        if path is not None:
            _ensure_target_topology(
                run_dir,
                scope=scope,
                destination=path,
            )
        if path is None or _file_sha256(path) != expected_base:
            raise PostRunTransactionConflictError(
                "Untargeted transaction authority changed after preparation."
            )


def _apply_target(
    run_dir: Path,
    journal: PostRunTransactionJournal,
    target: PostRunTransactionTarget,
    *,
    sessions_dir: Path,
    session_record: Path | None,
) -> None:
    destination = _target_destination(
        run_dir,
        target,
        session_record=session_record,
    )
    _ensure_target_topology(
        run_dir,
        scope=target.scope,
        destination=destination,
    )
    current_hash = _file_sha256(destination)
    if current_hash == target.target_sha256:
        current_payload = _read_exact_bytes(
            destination,
            allow_missing=False,
        )
        if current_payload is None:  # pragma: no cover - target hash exists
            raise PostRunTransactionIntegrityError(
                "Committed transaction target is missing."
            )
        _validate_structured_target(
            run_dir=run_dir,
            sessions_dir=sessions_dir,
            session_record=session_record,
            target=target,
            payload=current_payload,
            transaction_id=journal.transaction_id,
            operation_id=journal.operation_id,
            operation_type=journal.operation_type,
            chat_message_id=journal.chat_message_id,
        )
        return
    if current_hash != target.base_sha256:
        raise PostRunTransactionConflictError(
            "Transaction destination matches neither base nor target state."
        )
    staged_path = _staged_path(run_dir, target.staged_path)
    staged_payload = _read_exact_bytes(staged_path, allow_missing=False)
    if (
        staged_payload is None
        or post_run_payload_sha256(staged_payload) != target.target_sha256
    ):
        raise PostRunTransactionIntegrityError(
            "Staged transaction payload hash differs from its journal."
        )
    _validate_structured_target(
        run_dir=run_dir,
        sessions_dir=sessions_dir,
        session_record=session_record,
        target=target,
        payload=staged_payload,
        transaction_id=journal.transaction_id,
        operation_id=journal.operation_id,
        operation_type=journal.operation_type,
        chat_message_id=journal.chat_message_id,
    )
    atomic_write_bytes(destination, staged_payload)
    if _file_sha256(destination, allow_missing=False) != target.target_sha256:
        raise PostRunTransactionIntegrityError(
            "Post-run transaction destination did not retain target bytes."
        )


def _read_trace_payload(
    run_dir: Path,
    event: PostRunTransactionTraceEvent,
) -> dict[str, Any]:
    payload_bytes = _read_exact_bytes(
        _staged_path(run_dir, event.payload_path),
        allow_missing=False,
    )
    if (
        payload_bytes is None
        or post_run_payload_sha256(payload_bytes) != event.payload_sha256
    ):
        raise PostRunTransactionIntegrityError(
            "Staged trace payload hash differs from its journal."
        )
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PostRunTransactionIntegrityError(
            "Staged trace payload is invalid."
        ) from exc
    if (
        not isinstance(payload, dict)
        or canonical_trace_payload_bytes(payload) != payload_bytes
    ):
        raise PostRunTransactionIntegrityError(
            "Staged trace payload is not canonical."
        )
    return payload


def _verify_target_hashes(
    run_dir: Path,
    journal: PostRunTransactionJournal,
    *,
    session_record: Path | None,
) -> None:
    for target in journal.targets:
        destination = _target_destination(
            run_dir,
            target,
            session_record=session_record,
        )
        _ensure_target_topology(
            run_dir,
            scope=target.scope,
            destination=destination,
        )
        if _file_sha256(destination, allow_missing=False) != target.target_sha256:
            raise PostRunTransactionConflictError(
                "Completed transaction target differs from its journal."
            )


def _remove_completed_transaction(
    run_dir: Path,
    journal: PostRunTransactionJournal,
) -> None:
    journal_path = post_run_transaction_path(run_dir)
    try:
        synchronized_unlink(journal_path)
    except OSError:
        if inspect_entry(journal_path) is None:
            # The unlink happened but its directory synchronization was not
            # observed. Republish the complete intent so the next startup has
            # an unambiguous roll-forward authority.
            _write_journal(run_dir, journal)
        raise
    transaction_dir = _transaction_directory(
        run_dir,
        journal.transaction_id,
    )
    if transaction_dir.exists():
        remove_verified_tree(transaction_dir)


def apply_prepared_post_run_transaction(
    *,
    run_dir: Path,
    sessions_dir: Path,
) -> PostRunTransactionResult:
    """Roll one published transaction forward and remove its completed intent."""

    initial = read_post_run_transaction_journal(run_dir)
    session_record = (
        session_record_path(initial.session_id, sessions_dir=sessions_dir)
        if initial.session_id
        else None
    )
    with _transaction_locks(run_dir, session_record=session_record):
        journal = read_post_run_transaction_journal(run_dir)
        if journal.transaction_id != initial.transaction_id:
            raise PostRunTransactionConflictError(
                "Pending transaction changed before its locks were acquired."
            )
        require_real_directory(run_dir, label="Run directory")
        require_real_directory(
            _transaction_directory(run_dir, journal.transaction_id),
            label="Post-run transaction staging directory",
        )
        _verify_base_authorities(
            run_dir,
            journal,
            session_record=session_record,
        )

        for phase, completed_state in _PHASE_TRANSITIONS:
            for target in journal.targets:
                if target.phase == phase:
                    _apply_target(
                        run_dir,
                        journal,
                        target,
                        sessions_dir=sessions_dir,
                        session_record=session_record,
                    )
            if _STATE_ORDER.index(journal.state) < _STATE_ORDER.index(
                completed_state
            ):
                journal = _transition_journal(
                    run_dir,
                    journal,
                    completed_state,
                )

        trace_records: list[dict[str, Any]] = []
        base_cursor = TraceReadCursor(
            sequence=journal.base.trace_sequence,
            byte_offset=journal.base.trace_byte_offset,
        )
        for event in journal.trace_events:
            payload = _read_trace_payload(run_dir, event)
            try:
                record = append_trace_event_once(
                    Path(run_dir) / RUN_TRACE_FILENAME,
                    transaction_id=journal.transaction_id,
                    event_ordinal=event.ordinal,
                    event=event.event,
                    payload=payload,
                    base_cursor=base_cursor,
                    durability=event.durability,
                )
            except (TraceFormatError, TraceTransactionConflictError) as exc:
                raise PostRunTransactionConflictError(
                    "Transaction trace history conflicts with its journal."
                ) from exc
            trace_records.append(record)
        if _STATE_ORDER.index(journal.state) < _STATE_ORDER.index(
            "trace_committed"
        ):
            journal = _transition_journal(
                run_dir,
                journal,
                "trace_committed",
            )

        _verify_target_hashes(
            run_dir,
            journal,
            session_record=session_record,
        )
        if _STATE_ORDER.index(journal.state) < _STATE_ORDER.index("complete"):
            journal = _transition_journal(run_dir, journal, "complete")
        _remove_completed_transaction(run_dir, journal)
        return PostRunTransactionResult(
            transaction_id=journal.transaction_id,
            trace_records=tuple(trace_records),
        )


def execute_post_run_transaction(
    *,
    run_dir: Path,
    sessions_dir: Path,
    transaction_id: str,
    operation_id: str,
    operation_type: str,
    created_at_utc: str,
    targets: list[PostRunTargetPayload],
    trace_events: list[PostRunTraceEventPayload],
    session_id: str | None = None,
    chat_message_id: str | None = None,
) -> PostRunTransactionResult:
    session_record = (
        session_record_path(session_id, sessions_dir=sessions_dir)
        if session_id
        else None
    )
    with _transaction_locks(run_dir, session_record=session_record):
        prepare_post_run_transaction(
            run_dir=run_dir,
            sessions_dir=sessions_dir,
            transaction_id=transaction_id,
            operation_id=operation_id,
            operation_type=operation_type,
            created_at_utc=created_at_utc,
            targets=targets,
            trace_events=trace_events,
            session_id=session_id,
            chat_message_id=chat_message_id,
        )
        return apply_prepared_post_run_transaction(
            run_dir=run_dir,
            sessions_dir=sessions_dir,
        )


def recover_post_run_transactions(
    *,
    runs_dir: Path,
    sessions_dir: Path,
) -> tuple[int, list[PostRunTransactionRecoveryIssue]]:
    """Roll valid journals forward and report run-scoped invalid intents."""

    recovered = 0
    issues: list[PostRunTransactionRecoveryIssue] = []
    for entry in iter_directory_entries(runs_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        journal_entry = inspect_entry(
            entry.path / POST_RUN_TRANSACTION_FILENAME
        )
        if journal_entry is None:
            continue
        try:
            apply_prepared_post_run_transaction(
                run_dir=entry.path,
                sessions_dir=sessions_dir,
            )
        except (
            OSError,
            PostRunTransactionError,
            StoreTopologyError,
            TraceFormatError,
            ValidationError,
        ):
            issues.append(
                PostRunTransactionRecoveryIssue(
                    run_id=entry.path.name,
                    reason_code="invalid_post_run_transaction",
                )
            )
        else:
            recovered += 1
    return recovered, issues


def cleanup_orphaned_post_run_staging(
    runs_dir: Path,
) -> tuple[int, list[PostRunTransactionRecoveryIssue]]:
    """Remove staging left before journal publication or after journal removal."""

    removed = 0
    issues: list[PostRunTransactionRecoveryIssue] = []
    for entry in iter_directory_entries(runs_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        if inspect_entry(entry.path / POST_RUN_TRANSACTION_FILENAME) is not None:
            continue
        transactions_root = (
            entry.path / POST_RUN_TRANSACTION_STAGING_DIRECTORY
        )
        root_entry = inspect_entry(transactions_root)
        if root_entry is None:
            continue
        try:
            if root_entry.is_reparse or not root_entry.is_directory:
                raise StoreTopologyError(
                    "Post-run transaction staging root is unsafe."
                )
            for staged in list(iter_directory_entries(transactions_root)):
                if staged.is_reparse or not staged.is_directory:
                    raise StoreTopologyError(
                        "Post-run transaction staging entry is unsafe."
                    )
                remove_verified_tree(staged.path)
                removed += 1
            if not list(iter_directory_entries(transactions_root)):
                transactions_root.rmdir()
                synchronize_directory(transactions_root.parent)
        except (OSError, StoreTopologyError):
            issues.append(
                PostRunTransactionRecoveryIssue(
                    run_id=entry.path.name,
                    reason_code="invalid_post_run_transaction",
                )
            )
    return removed, issues


def committed_post_run_transaction_id(run_dir: Path) -> str | None:
    """Return the result-backed commit identity only when no journal is pending."""

    if inspect_entry(post_run_transaction_path(run_dir)) is not None:
        return None
    try:
        payload = _read_exact_bytes(
            Path(run_dir) / "result.json",
            allow_missing=True,
        )
        result = json.loads(payload.decode("utf-8")) if payload else None
    except (
        PostRunTransactionIntegrityError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return None
    metadata = (
        result.get(POST_RUN_RESULT_TRANSACTION_FIELD)
        if isinstance(result, dict)
        else None
    )
    try:
        if isinstance(result, dict):
            normalize_result_payload(result)
    except (TypeError, ValueError):
        return None
    transaction_id = (
        str(metadata.get("transaction_id") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    operation_id = (
        str(metadata.get("operation_id") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    operation_type = (
        str(metadata.get("operation_type") or "").strip()
        if isinstance(metadata, dict)
        else ""
    )
    return (
        transaction_id
        if all(
            _SAFE_ID.fullmatch(value)
            for value in (transaction_id, operation_id, operation_type)
        )
        else None
    )


def transaction_tagged_message_is_committed(
    message: dict[str, Any],
    *,
    committed_by_run: dict[str, str],
) -> bool:
    transaction_id = str(
        message.get("post_run_transaction_id") or ""
    ).strip()
    if not transaction_id:
        return True
    run_id = str(message.get("post_run_run_id") or "").strip()
    return bool(
        _SAFE_ID.fullmatch(transaction_id)
        and _SAFE_ID.fullmatch(run_id)
        and committed_by_run.get(run_id) == transaction_id
    )


def prune_orphaned_post_run_session_messages(
    *,
    runs_dir: Path,
    sessions_dir: Path,
) -> int:
    """Remove only transaction-tagged chat lacking a committed result identity."""

    committed_by_run = {
        entry.path.name: transaction_id
        for entry in iter_directory_entries(runs_dir)
        if not entry.is_reparse
        and entry.is_directory
        and (
            transaction_id := committed_post_run_transaction_id(entry.path)
        )
    }
    removed = 0
    for entry in iter_directory_entries(sessions_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        record_path = entry.path / SESSION_RECORD_FILENAME
        try:
            record = read_canonical_session_record(
                record_path,
                sessions_dir=sessions_dir,
            )
        except SessionRecordIntegrityError:
            continue
        messages = (
            record.get("chat_messages")
            if isinstance(record.get("chat_messages"), list)
            else []
        )
        retained = [
            message
            for message in messages
            if not isinstance(message, dict)
            or transaction_tagged_message_is_committed(
                message,
                committed_by_run=committed_by_run,
            )
        ]
        removed_here = len(messages) - len(retained)
        if not removed_here:
            continue
        with session_lock(record_path):
            latest = read_canonical_session_record(
                record_path,
                sessions_dir=sessions_dir,
            )
            latest_messages = (
                latest.get("chat_messages")
                if isinstance(latest.get("chat_messages"), list)
                else []
            )
            latest["chat_messages"] = [
                message
                for message in latest_messages
                if not isinstance(message, dict)
                or transaction_tagged_message_is_committed(
                    message,
                    committed_by_run=committed_by_run,
                )
            ]
            removed += len(latest_messages) - len(latest["chat_messages"])
            write_json_file(record_path, latest)
    return removed


__all__ = [
    "POST_RUN_RESULT_TRANSACTION_FIELD",
    "POST_RUN_TRANSACTION_ARTIFACT_KIND",
    "POST_RUN_TRANSACTION_PROTOCOL_VERSION",
    "POST_RUN_TRANSACTION_SCHEMA_VERSION",
    "POST_RUN_TRANSACTION_STAGING_DIRECTORY",
    "PostRunTargetPayload",
    "PostRunTraceEventPayload",
    "PostRunTransactionConflictError",
    "PostRunTransactionError",
    "PostRunTransactionIntegrityError",
    "PostRunTransactionJournal",
    "PostRunTransactionRecoveryIssue",
    "PostRunTransactionResult",
    "apply_prepared_post_run_transaction",
    "cleanup_orphaned_post_run_staging",
    "committed_post_run_transaction_id",
    "execute_post_run_transaction",
    "post_run_json_bytes",
    "post_run_payload_sha256",
    "prepare_post_run_transaction",
    "prune_orphaned_post_run_session_messages",
    "read_post_run_transaction_journal",
    "recover_post_run_transactions",
    "transaction_tagged_message_is_committed",
]
