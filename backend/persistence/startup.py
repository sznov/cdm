from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.api.settings import (
    RUN_RECORD_FILENAME,
    RUN_SPECIFICATION_FILENAME,
    RUN_TRACE_FILENAME,
    SESSION_RECORD_FILENAME,
)
from backend.persistence.common import read_json_file
from backend.persistence.post_run_transactions import (
    cleanup_orphaned_post_run_staging,
    prune_orphaned_post_run_session_messages,
    recover_post_run_transactions,
)
from backend.persistence.result_records import (
    reconcile_derived_result_artifacts,
    validate_result_record,
)
from backend.persistence.run_reconciliation import reconcile_inactive_running_run
from backend.persistence.run_path_references import (
    RUN_RELATIVE_PATH_REFERENCE_MODE,
    RunPathReferenceError,
    validate_recorded_run_path_references,
)
from backend.persistence.run_record_integrity import (
    RunRecordIntegrityError,
    read_canonical_run_record,
    validate_canonical_run_record,
    validate_canonical_run_record_context,
)
from backend.persistence.run_resume_materialization import (
    MATERIALIZED_RESUME_CHECKPOINT_REFERENCE,
)
from backend.persistence.run_specifications import (
    RunSpecificationIntegrityError,
    read_sealed_run_specification,
)
from backend.persistence.run_trace import (
    TraceFormatError,
    repair_incomplete_trace_tail,
    validate_trace,
)
from backend.persistence.session_record_integrity import (
    SessionRecordIntegrityError,
    validate_canonical_session_record,
    validate_canonical_session_record_context,
)
from backend.persistence.session_records import repair_session_job_index
from backend.persistence.startup_recovery import (
    RECOVERY_JOURNAL_FILENAME,
    STORE_MARKER_FILENAME,
    STORE_SCHEMA_VERSION,
    execute_recovery,
    inspect_store_marker,
    latest_recovery_summary,
    resume_recovery,
    write_current_store_marker,
)
from backend.persistence.store_topology import (
    StoreTopologyError,
    entry_exists,
    first_unsafe_tree_entry,
    inspect_entry,
    iter_directory_entries,
    iter_real_files,
    require_real_directory,
    require_safe_mutable_file,
)
from core.artifact_versions import ArtifactVersionError
from core.atomic_io import synchronized_mkdir, synchronized_rmdir, synchronized_unlink
from core.model_call_logger import is_model_call_reservation_name


def _temporary_artifacts(root: Path):
    if not entry_exists(root):
        return
    yield from (
        path
        for path in iter_real_files(root)
        if path.name.startswith(".") and path.name.endswith(".tmp")
    )


def cleanup_abandoned_atomic_writes(*roots: Path) -> int:
    removed = 0
    for root in roots:
        for path in _temporary_artifacts(root):
            try:
                synchronized_unlink(path)
                removed += 1
            except OSError:
                continue
    return removed


def cleanup_stale_model_call_reservations(runs_dir: Path) -> int:
    """Remove only empty reservations whose names prove logger ownership."""

    removed = 0
    if not entry_exists(runs_dir):
        return removed
    for entry in iter_directory_entries(runs_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        run_dir = entry.path
        model_calls_dir = run_dir / "model_calls"
        model_calls_entry = inspect_entry(model_calls_dir)
        if (
            model_calls_entry is None
            or model_calls_entry.is_reparse
            or not model_calls_entry.is_directory
        ):
            continue
        for pending_entry in iter_directory_entries(model_calls_dir):
            path = pending_entry.path
            if not is_model_call_reservation_name(path.name):
                continue
            try:
                if (
                    pending_entry.is_reparse
                    or not pending_entry.is_regular_file
                    or pending_entry.stat_result.st_size != 0
                ):
                    continue
                require_safe_mutable_file(
                    path,
                    label="Model-call reservation",
                )
                synchronized_unlink(path)
                removed += 1
            except (OSError, StoreTopologyError):
                continue
    return removed


def _cleanup_data_root_atomic_writes(data_root: Path) -> int:
    removed = 0
    for entry in iter_directory_entries(data_root):
        path = entry.path
        if (
            not path.name.startswith(".")
            or not path.name.endswith(".tmp")
            or entry.is_reparse
            or not entry.is_regular_file
        ):
            continue
        try:
            synchronized_unlink(path)
            removed += 1
        except OSError:
            continue
    return removed


def cleanup_unpublished_run_directories(runs_dir: Path) -> int:
    """Remove only directories left before canonical ``run.json`` publication."""

    removed = 0
    if not entry_exists(runs_dir):
        return removed
    for entry in iter_directory_entries(runs_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        run_dir = entry.path
        if (run_dir / RUN_RECORD_FILENAME).is_file():
            continue
        try:
            children = list(iter_directory_entries(run_dir))
            by_name = {child.path.name: child for child in children}
            if set(by_name) - {
                RUN_SPECIFICATION_FILENAME,
                "checkpoints",
            }:
                continue
            specification = by_name.get(RUN_SPECIFICATION_FILENAME)
            if (
                specification is None
                or specification.is_reparse
                or not specification.is_regular_file
            ):
                continue
            checkpoints = by_name.get("checkpoints")
            if checkpoints is not None:
                if checkpoints.is_reparse or not checkpoints.is_directory:
                    continue
                checkpoint_children = list(
                    iter_directory_entries(checkpoints.path)
                )
                expected_name = Path(
                    MATERIALIZED_RESUME_CHECKPOINT_REFERENCE
                ).name
                if (
                    len(checkpoint_children) != 1
                    or checkpoint_children[0].path.name != expected_name
                    or checkpoint_children[0].is_reparse
                    or not checkpoint_children[0].is_regular_file
                ):
                    continue
                synchronized_unlink(checkpoint_children[0].path)
                synchronized_rmdir(checkpoints.path)
            synchronized_unlink(specification.path)
            synchronized_rmdir(run_dir)
            removed += 1
        except (OSError, StoreTopologyError):
            continue
    return removed


def _unsafe_family_candidates(
    runs_dir: Path,
    sessions_dir: Path,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for root, kind in ((runs_dir, "run"), (sessions_dir, "session")):
        for entry in iter_directory_entries(root):
            unsafe = entry.is_reparse or not entry.is_directory
            if not unsafe:
                unsafe = first_unsafe_tree_entry(entry.path) is not None
            if not unsafe:
                continue
            candidates.append(
                _candidate(
                    f"{root.name}/{entry.path.name}",
                    kind=kind,
                    identifier=entry.path.name,
                    reason_code="unsafe_store_topology",
                )
            )
    return candidates


def _require_safe_store_roots(
    data_root: Path,
    runs_dir: Path,
    sessions_dir: Path,
) -> None:
    require_real_directory(data_root, label="Application data root")
    for root, label in (
        (runs_dir, "Runs directory"),
        (sessions_dir, "Sessions directory"),
        (data_root / "archive", "Recovery archive directory"),
    ):
        if entry_exists(root):
            require_real_directory(root, label=label)
    for path, label in (
        (data_root / RECOVERY_JOURNAL_FILENAME, "Recovery journal"),
        (data_root / STORE_MARKER_FILENAME, "Application store marker"),
    ):
        if entry_exists(path):
            require_safe_mutable_file(path, label=label)


def _candidate(
    source: str,
    *,
    kind: str,
    identifier: str,
    reason_code: str,
) -> dict[str, str]:
    return {
        "source": source,
        "kind": kind,
        "identifier": identifier,
        "reason_code": reason_code,
    }


def _session_candidate(session_dir: Path) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    source = f"sessions/{session_dir.name}"
    record_path = session_dir / SESSION_RECORD_FILENAME
    if not record_path.is_file():
        return None, _candidate(
            source,
            kind="session",
            identifier=session_dir.name,
            reason_code="missing_session_record",
        )
    try:
        payload = read_json_file(record_path)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, _candidate(
            source,
            kind="session",
            identifier=session_dir.name,
            reason_code="invalid_session_json",
        )
    except OSError:
        return None, _candidate(
            source,
            kind="session",
            identifier=session_dir.name,
            reason_code="unreadable_session_record",
        )
    try:
        record = validate_canonical_session_record(payload)
        validate_canonical_session_record_context(
            record,
            record_path=record_path,
            sessions_dir=session_dir.parent,
        )
    except SessionRecordIntegrityError as exc:
        return None, _candidate(
            source,
            kind="session",
            identifier=session_dir.name,
            reason_code=exc.reason_code,
        )
    return record, None


def _run_candidate(
    run_dir: Path,
) -> tuple[dict[str, Any] | None, dict[str, str] | None, bool]:
    source = f"runs/{run_dir.name}"
    record_path = run_dir / RUN_RECORD_FILENAME
    if not record_path.is_file():
        return None, _candidate(
            source,
            kind="run",
            identifier=run_dir.name,
            reason_code="missing_run_record",
        ), False
    try:
        payload = read_json_file(record_path)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, _candidate(
            source,
            kind="run",
            identifier=run_dir.name,
            reason_code="invalid_run_json",
        ), False
    except OSError:
        return None, _candidate(
            source,
            kind="run",
            identifier=run_dir.name,
            reason_code="unreadable_run_record",
        ), False
    try:
        record = validate_canonical_run_record(payload)
        validate_canonical_run_record_context(
            record,
            record_path=record_path,
            runs_dir=run_dir.parent,
        )
    except RunRecordIntegrityError as exc:
        return None, _candidate(
            source,
            kind="run",
            identifier=run_dir.name,
            reason_code=exc.reason_code,
        ), False
    if str(record.get("job_id") or "") != run_dir.name:
        return None, _candidate(
            source,
            kind="run",
            identifier=run_dir.name,
            reason_code="invalid_run_record",
        ), False

    try:
        read_sealed_run_specification(run_dir, record)
    except RunSpecificationIntegrityError as exc:
        return None, _candidate(
            source,
            kind="run",
            identifier=run_dir.name,
            reason_code=exc.reason_code,
        ), False

    path_reference_mode = record.get("path_reference_mode")
    if path_reference_mode not in {None, RUN_RELATIVE_PATH_REFERENCE_MODE}:
        return None, _candidate(
            source,
            kind="run",
            identifier=run_dir.name,
            reason_code="invalid_run_path_reference",
        ), False
    try:
        validate_recorded_run_path_references(
            record,
            run_dir=run_dir,
            mode=path_reference_mode,
            excluded_keys=frozenset({"resume_checkpoint_path"}),
        )
    except RunPathReferenceError:
        return None, _candidate(
            source,
            kind="run",
            identifier=run_dir.name,
            reason_code="invalid_run_path_reference",
        ), False

    repaired_trace_tail = False
    if (run_dir / "result.json").exists():
        try:
            result_record = validate_result_record(run_dir)
            validate_recorded_run_path_references(
                result_record,
                run_dir=run_dir,
                mode=path_reference_mode,
            )
        except ArtifactVersionError:
            reason = "unsupported_result_record_version"
        except RunPathReferenceError:
            reason = "invalid_result_path_reference"
        except (
            AttributeError,
            TypeError,
            ValueError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            reason = "invalid_result_record"
        else:
            reason = ""
        if reason:
            return None, _candidate(
                source,
                kind="run",
                identifier=run_dir.name,
                reason_code=reason,
            ), False

    trace_path = run_dir / RUN_TRACE_FILENAME
    if trace_path.exists():
        try:
            repaired_trace_tail = repair_incomplete_trace_tail(trace_path)
            validate_trace(trace_path)
        except TraceFormatError:
            reason = "malformed_complete_trace"
        except OSError:
            reason = "unreadable_trace"
        else:
            reason = ""
        if reason:
            return None, _candidate(
                source,
                kind="run",
                identifier=run_dir.name,
                reason_code=reason,
            ), repaired_trace_tail
    return record, None, repaired_trace_tail


def _inspect_record_families(
    runs_dir: Path,
    sessions_dir: Path,
    *,
    initial_candidates: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, str]], int]:
    candidates: list[dict[str, str]] = list(initial_candidates or [])
    repaired_trace_tails = 0
    valid_session_ids: set[str] = set()
    for entry in iter_directory_entries(sessions_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        session_dir = entry.path
        record, candidate = _session_candidate(session_dir)
        if candidate is not None:
            candidates.append(candidate)
        elif record is not None:
            valid_session_ids.add(str(record["session_id"]))

    valid_runs: list[tuple[Path, dict[str, Any]]] = []
    for entry in iter_directory_entries(runs_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        run_dir = entry.path
        record, candidate, repaired = _run_candidate(run_dir)
        repaired_trace_tails += int(repaired)
        if candidate is not None:
            candidates.append(candidate)
        elif record is not None:
            valid_runs.append((run_dir, record))

    for run_dir, record in valid_runs:
        session_id = str(record.get("session_id") or "")
        if session_id and session_id not in valid_session_ids:
            candidates.append(
                _candidate(
                    f"runs/{run_dir.name}",
                    kind="run",
                    identifier=run_dir.name,
                    reason_code="missing_session_dependency",
                )
            )

    valid_runs_by_id = {
        str(record.get("job_id") or run_dir.name): (run_dir, record)
        for run_dir, record in valid_runs
    }
    unavailable_run_ids = {
        candidate["identifier"]
        for candidate in candidates
        if candidate["kind"] == "run"
    }
    changed = True
    while changed:
        changed = False
        for job_id, (run_dir, record) in valid_runs_by_id.items():
            if job_id in unavailable_run_ids:
                continue
            request = (
                record.get("request")
                if isinstance(record.get("request"), dict)
                else {}
            )
            source_job_id = str(
                request.get("resume_from_job_id") or ""
            ).strip()
            is_legacy_resume = bool(
                source_job_id
                and request.get("resume_checkpoint_mode") in {None, ""}
            )
            if not is_legacy_resume:
                continue
            if (
                source_job_id in valid_runs_by_id
                and source_job_id not in unavailable_run_ids
            ):
                continue
            candidates.append(
                _candidate(
                    f"runs/{run_dir.name}",
                    kind="run",
                    identifier=run_dir.name,
                    reason_code="legacy_resume_dependency_unavailable",
                )
            )
            unavailable_run_ids.add(job_id)
            changed = True
    unique_candidates: dict[str, dict[str, str]] = {}
    for candidate in candidates:
        unique_candidates.setdefault(candidate["source"], candidate)
    return (
        sorted(
            unique_candidates.values(),
            key=lambda item: (0 if item["kind"] == "run" else 1, item["source"]),
        ),
        repaired_trace_tails,
    )


def _archive_unsupported_store(
    data_root: Path,
    *,
    store_version: int,
) -> dict[str, Any]:
    moves: list[dict[str, str]] = []
    for name in ("runs", "sessions", STORE_MARKER_FILENAME):
        if not (data_root / name).exists():
            continue
        moves.append(
            _candidate(
                name,
                kind="store_component",
                identifier=name,
                reason_code=f"unsupported_store_schema_{store_version}",
            )
        )
    return execute_recovery(data_root, operation="archive_store", moves=moves)


def _reconcile_current_runs(runs_dir: Path) -> tuple[int, int, int]:
    reconciled_runs = 0
    rebuilt_artifacts = 0
    repaired_trace_tails = 0
    for entry in iter_directory_entries(runs_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        run_dir = entry.path
        if repair_incomplete_trace_tail(run_dir / RUN_TRACE_FILENAME):
            repaired_trace_tails += 1
        record = read_canonical_run_record(
            run_dir / RUN_RECORD_FILENAME,
            runs_dir=runs_dir,
        )
        before_status = record.get("status")
        record = reconcile_inactive_running_run(
            run_dir,
            record,
            active_run_ids=(),
        )
        if record.get("status") != before_status:
            reconciled_runs += 1
        rebuilt_artifacts += len(reconcile_derived_result_artifacts(run_dir))
    return reconciled_runs, rebuilt_artifacts, repaired_trace_tails


def _repair_session_job_indexes(runs_dir: Path, sessions_dir: Path) -> int:
    runs_by_session: dict[str, list[tuple[str, str]]] = {}
    for entry in iter_directory_entries(runs_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        run_dir = entry.path
        record = read_canonical_run_record(
            run_dir / RUN_RECORD_FILENAME,
            runs_dir=runs_dir,
        )
        session_id = str(record.get("session_id") or "")
        if not session_id:
            continue
        timestamp = str(
            record.get("queued_at_utc")
            or record.get("started_at_utc")
            or record.get("completed_at_utc")
            or ""
        )
        runs_by_session.setdefault(session_id, []).append(
            (timestamp, str(record["job_id"]))
        )

    repaired = 0
    for entry in iter_directory_entries(sessions_dir):
        if entry.is_reparse or not entry.is_directory:
            continue
        session_dir = entry.path
        session_id = session_dir.name
        ordered = sorted(runs_by_session.get(session_id, []))
        repaired += int(
            repair_session_job_index(
                session_id,
                [job_id for _timestamp, job_id in ordered],
                sessions_dir=sessions_dir,
            )
        )
    return repaired


def maintain_application_records(runs_dir: Path, sessions_dir: Path) -> dict[str, Any]:
    """Inspect, recover, and reconcile the single-owner application store."""

    data_root = runs_dir.parent
    if sessions_dir.parent != data_root:
        raise ValueError("Run and session directories must share one application data root.")
    synchronized_mkdir(data_root, parents=True, exist_ok=True)
    _require_safe_store_roots(data_root, runs_dir, sessions_dir)

    recovery_summary = resume_recovery(data_root)
    store_version = inspect_store_marker(data_root)
    if store_version is not None and store_version != STORE_SCHEMA_VERSION:
        recovery_summary = _archive_unsupported_store(
            data_root,
            store_version=store_version,
        )
        store_version = STORE_SCHEMA_VERSION

    synchronized_mkdir(runs_dir, parents=True, exist_ok=True)
    synchronized_mkdir(sessions_dir, parents=True, exist_ok=True)
    _require_safe_store_roots(data_root, runs_dir, sessions_dir)

    unsafe_candidates = _unsafe_family_candidates(runs_dir, sessions_dir)
    if unsafe_candidates:
        recovery_summary = execute_recovery(
            data_root,
            operation="quarantine",
            moves=unsafe_candidates,
        )

    recovered_post_run_transactions, transaction_issues = (
        recover_post_run_transactions(
            runs_dir=runs_dir,
            sessions_dir=sessions_dir,
        )
    )
    transaction_candidates = [
        _candidate(
            f"runs/{issue.run_id}",
            kind="run",
            identifier=issue.run_id,
            reason_code=issue.reason_code,
        )
        for issue in transaction_issues
    ]
    removed_post_run_staging, staging_issues = (
        cleanup_orphaned_post_run_staging(runs_dir)
    )
    transaction_candidates.extend(
        _candidate(
            f"runs/{issue.run_id}",
            kind="run",
            identifier=issue.run_id,
            reason_code=issue.reason_code,
        )
        for issue in staging_issues
    )

    removed_temporaries = cleanup_abandoned_atomic_writes(
        runs_dir,
        sessions_dir,
    )
    removed_temporaries += _cleanup_data_root_atomic_writes(data_root)
    removed_model_call_reservations = cleanup_stale_model_call_reservations(
        runs_dir
    )
    removed_unpublished_runs = cleanup_unpublished_run_directories(runs_dir)

    candidates, inspected_trace_repairs = _inspect_record_families(
        runs_dir,
        sessions_dir,
        initial_candidates=transaction_candidates,
    )
    if candidates:
        recovery_summary = execute_recovery(
            data_root,
            operation="quarantine",
            moves=candidates,
        )
    removed_orphaned_transaction_messages = (
        prune_orphaned_post_run_session_messages(
            runs_dir=runs_dir,
            sessions_dir=sessions_dir,
        )
    )

    if store_version is None:
        write_current_store_marker(data_root)

    reconciled_runs, rebuilt_artifacts, reconciled_trace_repairs = (
        _reconcile_current_runs(runs_dir)
    )
    rebuilt_session_indexes = _repair_session_job_indexes(runs_dir, sessions_dir)
    repaired_trace_tails = inspected_trace_repairs + reconciled_trace_repairs
    visible_recovery = recovery_summary or latest_recovery_summary(data_root)
    return {
        "store_schema_version": STORE_SCHEMA_VERSION,
        "startup_recovery": visible_recovery,
        "removed_temporaries": removed_temporaries,
        "removed_model_call_reservations": removed_model_call_reservations,
        "removed_unpublished_runs": removed_unpublished_runs,
        "recovered_post_run_transactions": recovered_post_run_transactions,
        "removed_post_run_staging": removed_post_run_staging,
        "removed_orphaned_transaction_messages": (
            removed_orphaned_transaction_messages
        ),
        "reconciled_runs": reconciled_runs,
        "rebuilt_artifacts": rebuilt_artifacts,
        "rebuilt_session_indexes": rebuilt_session_indexes,
        "repaired_trace_tails": repaired_trace_tails,
    }


__all__ = [
    "cleanup_abandoned_atomic_writes",
    "cleanup_stale_model_call_reservations",
    "cleanup_unpublished_run_directories",
    "maintain_application_records",
]
