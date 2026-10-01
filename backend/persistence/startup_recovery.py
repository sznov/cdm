from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from backend.persistence.common import read_json_file, utc_now_iso, write_json_file
from backend.persistence.store_topology import (
    StoreTopologyError,
    ensure_real_directory_chain,
    entry_exists,
    inspect_entry,
    iter_directory_entries,
    require_real_directory,
    require_safe_mutable_file,
    validate_relative_components,
)
from core.atomic_io import (
    synchronize_directory,
    synchronized_replace,
    synchronized_unlink,
)


STORE_MARKER_FILENAME = "store.json"
RECOVERY_JOURNAL_FILENAME = "recovery-journal.json"
RECOVERY_MANIFEST_FILENAME = "recovery-manifest.json"
STORE_SCHEMA_VERSION = 1
RECOVERY_SCHEMA_VERSION = 1

_STORE_ARTIFACT_KIND = "application_store"
_RECOVERY_ID = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
_RECOVERY_OPERATIONS = frozenset({"quarantine", "archive_store"})
_MOVE_KINDS = frozenset({"run", "session", "store_component"})


class StoreRecoveryError(RuntimeError):
    """Raised when startup cannot recover the store without guessing."""


def empty_recovery_summary() -> dict[str, Any]:
    return {
        "occurred": False,
        "recovery_id": None,
        "operation": None,
        "quarantined_runs": 0,
        "quarantined_sessions": 0,
        "archived_store": False,
        "reason_counts": {},
        "message": "",
    }


def current_store_marker() -> dict[str, Any]:
    return {
        "artifact_kind": _STORE_ARTIFACT_KIND,
        "schema_version": STORE_SCHEMA_VERSION,
    }


def inspect_store_marker(data_root: Path) -> int | None:
    """Return the explicit store version, or ``None`` for an unmarked store."""

    path = data_root / STORE_MARKER_FILENAME
    if not entry_exists(path):
        return None
    try:
        require_safe_mutable_file(path, label="Application store marker")
    except StoreTopologyError as exc:
        raise StoreRecoveryError(
            "The application store marker is unsafe; no records were moved."
        ) from exc
    try:
        marker = read_json_file(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StoreRecoveryError(
            "The application store marker is unreadable; no records were moved."
        ) from exc
    if (
        not isinstance(marker, dict)
        or set(marker) != {"artifact_kind", "schema_version"}
        or marker.get("artifact_kind") != _STORE_ARTIFACT_KIND
        or isinstance(marker.get("schema_version"), bool)
        or not isinstance(marker.get("schema_version"), int)
        or marker["schema_version"] < 1
    ):
        raise StoreRecoveryError(
            "The application store marker is malformed; no records were moved."
        )
    return int(marker["schema_version"])


def write_current_store_marker(data_root: Path) -> None:
    require_real_directory(data_root, label="Application data root")
    write_json_file(data_root / STORE_MARKER_FILENAME, current_store_marker())


def _recovery_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:12]}"


def _safe_relative_path(value: object, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise StoreRecoveryError(f"Recovery journal field {field!r} is invalid.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in value
    ):
        raise StoreRecoveryError(f"Recovery journal field {field!r} is unsafe.")
    return path


def _validate_move(
    move: object,
    *,
    operation: str,
    destination_root: PurePosixPath,
) -> dict[str, str]:
    if not isinstance(move, dict) or set(move) != {
        "source",
        "destination",
        "kind",
        "identifier",
        "reason_code",
    }:
        raise StoreRecoveryError("Recovery journal contains an invalid move.")
    source = _safe_relative_path(move.get("source"), field="source")
    destination = _safe_relative_path(move.get("destination"), field="destination")
    kind = move.get("kind")
    identifier = move.get("identifier")
    reason_code = move.get("reason_code")
    if (
        kind not in _MOVE_KINDS
        or not isinstance(identifier, str)
        or not identifier
        or not isinstance(reason_code, str)
        or not reason_code
    ):
        raise StoreRecoveryError("Recovery journal contains invalid move metadata.")
    if destination.parts[: len(destination_root.parts)] != destination_root.parts:
        raise StoreRecoveryError("Recovery destination escapes its recovery directory.")
    if destination.parts[len(destination_root.parts) :] != source.parts:
        raise StoreRecoveryError("Recovery destination does not preserve its source path.")
    if operation == "quarantine":
        expected_kind = "run" if source.parts[0] == "runs" else "session"
        if (
            len(source.parts) != 2
            or source.parts[0] not in {"runs", "sessions"}
            or kind != expected_kind
            or identifier != source.parts[1]
        ):
            raise StoreRecoveryError("Quarantine journal contains an invalid record family.")
    elif (
        source.as_posix() not in {"runs", "sessions", STORE_MARKER_FILENAME}
        or kind != "store_component"
    ):
        raise StoreRecoveryError("Whole-store recovery journal contains an invalid component.")
    return {
        "source": source.as_posix(),
        "destination": destination.as_posix(),
        "kind": kind,
        "identifier": identifier,
        "reason_code": reason_code,
    }


def _validate_journal(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "recovery_id",
        "operation",
        "created_at_utc",
        "destination_root",
        "moves",
    }:
        raise StoreRecoveryError("Recovery journal has an unsupported shape.")
    if payload.get("schema_version") != RECOVERY_SCHEMA_VERSION:
        raise StoreRecoveryError("Recovery journal has an unsupported version.")
    recovery_id = payload.get("recovery_id")
    operation = payload.get("operation")
    created_at_utc = payload.get("created_at_utc")
    moves = payload.get("moves")
    if (
        not isinstance(recovery_id, str)
        or not _RECOVERY_ID.fullmatch(recovery_id)
        or operation not in _RECOVERY_OPERATIONS
        or not isinstance(created_at_utc, str)
        or not created_at_utc
        or not isinstance(moves, list)
        or not moves
    ):
        raise StoreRecoveryError("Recovery journal contains invalid metadata.")
    destination_root = _safe_relative_path(
        payload.get("destination_root"),
        field="destination_root",
    )
    if destination_root.as_posix() != f"archive/recovery-{recovery_id}":
        raise StoreRecoveryError("Recovery journal destination is not canonical.")
    validated_moves = [
        _validate_move(
            move,
            operation=operation,
            destination_root=destination_root,
        )
        for move in moves
    ]
    sources = [move["source"].casefold() for move in validated_moves]
    destinations = [move["destination"].casefold() for move in validated_moves]
    if len(sources) != len(set(sources)) or len(destinations) != len(set(destinations)):
        raise StoreRecoveryError("Recovery journal contains duplicate paths.")
    return {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "recovery_id": recovery_id,
        "operation": operation,
        "created_at_utc": created_at_utc,
        "destination_root": destination_root.as_posix(),
        "moves": validated_moves,
    }


def _summary_from_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    moves = manifest.get("moves") if isinstance(manifest.get("moves"), list) else []
    operation = str(manifest.get("operation") or "")
    reason_counts = Counter(
        str(move.get("reason_code"))
        for move in moves
        if isinstance(move, dict) and move.get("reason_code")
    )
    run_count = sum(
        1 for move in moves if isinstance(move, dict) and move.get("kind") == "run"
    )
    session_count = sum(
        1 for move in moves if isinstance(move, dict) and move.get("kind") == "session"
    )
    if operation == "archive_store":
        message = (
            "An incompatible application store was archived, and a new active "
            "store was created."
        )
    else:
        parts: list[str] = []
        if session_count:
            parts.append(f"{session_count} session{'s' if session_count != 1 else ''}")
        if run_count:
            parts.append(f"{run_count} run{'s' if run_count != 1 else ''}")
        moved = " and ".join(parts) or "Corrupt records"
        verb = "was" if run_count + session_count == 1 else "were"
        message = (
            f"{moved} {verb} moved to recovery storage. "
            "Other history remains available."
        )
    return {
        "occurred": True,
        "recovery_id": manifest.get("recovery_id"),
        "operation": operation,
        "quarantined_runs": run_count,
        "quarantined_sessions": session_count,
        "archived_store": operation == "archive_store",
        "reason_counts": dict(sorted(reason_counts.items())),
        "message": message,
    }


def _validate_manifest(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "recovery_id",
        "operation",
        "created_at_utc",
        "completed_at_utc",
        "counts",
        "reason_counts",
        "moves",
    }:
        raise StoreRecoveryError("Recovery manifest has an unsupported shape.")
    recovery_id = payload.get("recovery_id")
    operation = payload.get("operation")
    created_at_utc = payload.get("created_at_utc")
    completed_at_utc = payload.get("completed_at_utc")
    if (
        payload.get("schema_version") != RECOVERY_SCHEMA_VERSION
        or not isinstance(recovery_id, str)
        or not _RECOVERY_ID.fullmatch(recovery_id)
        or operation not in _RECOVERY_OPERATIONS
        or not isinstance(created_at_utc, str)
        or not created_at_utc
        or not isinstance(completed_at_utc, str)
        or not completed_at_utc
    ):
        raise StoreRecoveryError("Recovery manifest contains invalid metadata.")
    destination_root = PurePosixPath(f"archive/recovery-{recovery_id}")
    moves_payload = payload.get("moves")
    if not isinstance(moves_payload, list) or not moves_payload:
        raise StoreRecoveryError("Recovery manifest contains no moves.")
    moves = [
        _validate_move(
            move,
            operation=operation,
            destination_root=destination_root,
        )
        for move in moves_payload
    ]
    kinds = Counter(move["kind"] for move in moves)
    expected_counts = {
        "runs": kinds["run"],
        "sessions": kinds["session"],
        "store_components": kinds["store_component"],
        "total": len(moves),
    }
    expected_reasons = dict(
        sorted(Counter(move["reason_code"] for move in moves).items())
    )
    if (
        payload.get("counts") != expected_counts
        or payload.get("reason_counts") != expected_reasons
    ):
        raise StoreRecoveryError("Recovery manifest counts do not match its moves.")
    return {
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "recovery_id": recovery_id,
        "operation": operation,
        "created_at_utc": created_at_utc,
        "completed_at_utc": completed_at_utc,
        "counts": expected_counts,
        "reason_counts": expected_reasons,
        "moves": moves,
    }


def _manifest_for_journal(journal: dict[str, Any]) -> dict[str, Any]:
    kinds = Counter(move["kind"] for move in journal["moves"])
    reasons = Counter(move["reason_code"] for move in journal["moves"])
    return _validate_manifest({
        "schema_version": RECOVERY_SCHEMA_VERSION,
        "recovery_id": journal["recovery_id"],
        "operation": journal["operation"],
        "created_at_utc": journal["created_at_utc"],
        "completed_at_utc": utc_now_iso(),
        "counts": {
            "runs": kinds["run"],
            "sessions": kinds["session"],
            "store_components": kinds["store_component"],
            "total": len(journal["moves"]),
        },
        "reason_counts": dict(sorted(reasons.items())),
        "moves": [dict(move) for move in journal["moves"]],
    })


def _move_recovery_path(source: Path, destination: Path) -> None:
    synchronized_replace(source, destination)


def resume_recovery(data_root: Path) -> dict[str, Any] | None:
    journal_path = data_root / RECOVERY_JOURNAL_FILENAME
    require_real_directory(data_root, label="Application data root")
    if not entry_exists(journal_path):
        return None
    try:
        require_safe_mutable_file(journal_path, label="Recovery journal")
        journal = _validate_journal(read_json_file(journal_path))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        StoreTopologyError,
    ) as exc:
        raise StoreRecoveryError(
            "The recovery journal is unreadable; no additional records were moved."
        ) from exc

    for move in journal["moves"]:
        source = data_root / PurePosixPath(move["source"])
        destination = data_root / PurePosixPath(move["destination"])
        try:
            validate_relative_components(
                data_root,
                move["source"],
                allow_final_reparse=True,
            )
            validate_relative_components(
                data_root,
                move["destination"],
                allow_final_reparse=True,
            )
        except StoreTopologyError as exc:
            raise StoreRecoveryError(
                "Recovery path topology is unsafe; no additional records were moved."
            ) from exc
        source_exists = entry_exists(source)
        destination_exists = entry_exists(destination)
        if source_exists and destination_exists:
            raise StoreRecoveryError(
                f"Recovery found both source and destination for {move['identifier']!r}."
            )
        if not source_exists and not destination_exists:
            raise StoreRecoveryError(
                f"Recovery cannot locate {move['identifier']!r} at either recorded path."
            )
        if source_exists:
            try:
                ensure_real_directory_chain(data_root, destination.parent)
            except StoreTopologyError as exc:
                raise StoreRecoveryError(
                    "Recovery destination topology is unsafe; no record was moved."
                ) from exc
            _move_recovery_path(source, destination)
        else:
            # A previous attempt may have completed the rename but failed while
            # synchronizing either directory. Re-establish both sides before
            # publishing the manifest and removing the recovery journal.
            synchronize_directory(destination.parent)
            if source.parent != destination.parent:
                synchronize_directory(source.parent)

    destination_root = data_root / PurePosixPath(journal["destination_root"])
    try:
        ensure_real_directory_chain(data_root, destination_root)
    except StoreTopologyError as exc:
        raise StoreRecoveryError(
            "Recovery destination topology is unsafe."
        ) from exc
    manifest = _manifest_for_journal(journal)
    write_json_file(destination_root / RECOVERY_MANIFEST_FILENAME, manifest)

    if journal["operation"] == "archive_store":
        ensure_real_directory_chain(data_root, data_root / "runs")
        ensure_real_directory_chain(data_root, data_root / "sessions")
        write_current_store_marker(data_root)

    synchronized_unlink(journal_path)
    return _summary_from_manifest(manifest)


def execute_recovery(
    data_root: Path,
    *,
    operation: str,
    moves: list[dict[str, str]],
) -> dict[str, Any]:
    if operation not in _RECOVERY_OPERATIONS or not moves:
        raise ValueError("A recovery operation requires a supported operation and moves.")
    journal_path = data_root / RECOVERY_JOURNAL_FILENAME
    require_real_directory(data_root, label="Application data root")
    if entry_exists(journal_path):
        raise StoreRecoveryError("A recovery journal is already active.")
    recovery_id = _recovery_id()
    destination_root = f"archive/recovery-{recovery_id}"
    journal_moves = [
        {
            **move,
            "destination": f"{destination_root}/{move['source']}",
        }
        for move in moves
    ]
    journal = _validate_journal(
        {
            "schema_version": RECOVERY_SCHEMA_VERSION,
            "recovery_id": recovery_id,
            "operation": operation,
            "created_at_utc": utc_now_iso(),
            "destination_root": destination_root,
            "moves": journal_moves,
        }
    )
    # This atomic publication happens before the first record move.
    write_json_file(journal_path, journal)
    summary = resume_recovery(data_root)
    if summary is None:  # pragma: no cover - the journal was just published
        raise StoreRecoveryError("Recovery journal disappeared before execution.")
    return summary


def latest_recovery_summary(data_root: Path) -> dict[str, Any]:
    archive_root = data_root / "archive"
    archive_entry = inspect_entry(archive_root)
    if archive_entry is None:
        return empty_recovery_summary()
    if archive_entry.is_reparse or not archive_entry.is_directory:
        raise StoreRecoveryError("Recovery archive topology is unsafe.")
    manifests: list[dict[str, Any]] = []
    for recovery_entry in iter_directory_entries(archive_root):
        if (
            recovery_entry.is_reparse
            or not recovery_entry.is_directory
            or not recovery_entry.path.name.startswith("recovery-")
        ):
            continue
        path = recovery_entry.path / RECOVERY_MANIFEST_FILENAME
        manifest_entry = inspect_entry(path)
        if (
            manifest_entry is None
            or manifest_entry.is_reparse
            or not manifest_entry.is_regular_file
        ):
            continue
        try:
            manifests.append(_validate_manifest(read_json_file(path)))
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            StoreRecoveryError,
        ):
            continue
    if manifests:
        latest = max(
            manifests,
            key=lambda item: (item["completed_at_utc"], item["recovery_id"]),
        )
        return _summary_from_manifest(latest)
    return empty_recovery_summary()


__all__ = [
    "RECOVERY_JOURNAL_FILENAME",
    "RECOVERY_MANIFEST_FILENAME",
    "RECOVERY_SCHEMA_VERSION",
    "STORE_MARKER_FILENAME",
    "STORE_SCHEMA_VERSION",
    "StoreRecoveryError",
    "current_store_marker",
    "empty_recovery_summary",
    "execute_recovery",
    "inspect_store_marker",
    "latest_recovery_summary",
    "resume_recovery",
    "write_current_store_marker",
]
