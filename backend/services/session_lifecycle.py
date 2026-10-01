from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from harnesses import get_harness_template

from backend.api.models import SessionCreateRequest, SessionPatchRequest
from backend.api.settings import RUN_RECORD_FILENAME
from backend.persistence.common import utc_now_iso, write_json_file
from backend.persistence.locks import run_locks, session_lock
from backend.persistence.run_record_integrity import (
    RunRecordIntegrityError,
    read_canonical_run_record,
)
from backend.persistence.session_paths import (
    make_session_id,
    safe_session_dir,
    session_record_path,
)
from backend.persistence.session_records import (
    generated_session_title,
    mutate_session_record,
    read_session_record,
)
from backend.persistence.store_topology import (
    StoreTopologyError,
    entry_exists,
    first_unsafe_tree_entry,
    iter_directory_entries,
    remove_verified_tree,
    require_real_directory,
)
from backend.persistence.session_record_integrity import (
    validate_canonical_session_record,
    validate_canonical_session_record_context,
)
from backend.services.runtime_harness_spec import workflow_runtime_config_from_effective
from backend.services.runtime_session_resolution import materialized_session_harness_spec
from backend.services.session_queries import (
    session_payload_from_runs,
    session_run_records_by_session,
    summarize_session_payload,
)
from core.artifact_versions import add_session_record_version
from core.model_bindings import normalize_model_bindings
from core.providers.factory import provider_descriptor
from core.statuses import run_status_is_active


def _strict_stored_run_records(
    runs_dir: Path,
) -> list[tuple[Path, dict[str, Any]]]:
    if not entry_exists(runs_dir):
        return []
    records: list[tuple[Path, dict[str, Any]]] = []
    try:
        for entry in iter_directory_entries(runs_dir):
            if entry.is_reparse or not entry.is_directory:
                raise StoreTopologyError("Run family entry is unsafe.")
            record = read_canonical_run_record(
                entry.path / RUN_RECORD_FILENAME,
                runs_dir=runs_dir,
            )
            records.append((entry.path, record))
    except (RunRecordIntegrityError, StoreTopologyError) as exc:
        raise HTTPException(
            status_code=409,
            detail="session_deletion_integrity_error",
        ) from exc
    return records


def create_modeling_session(request: SessionCreateRequest, *, sessions_dir: Path) -> dict[str, Any]:
    template = get_harness_template(request.runtime_harness_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Runtime harness not found.")
    if not template.get("runnable"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Runtime harness '{request.runtime_harness_id}' is not available in the "
                "browser application. Use its script entry point instead."
            ),
        )

    spec = materialized_session_harness_spec(request)
    model_bindings = normalize_model_bindings(spec.model_dump(mode="json")["model_bindings"])
    default_binding = model_bindings["default"]
    provider = str(default_binding["provider"])
    provider_label = provider_descriptor(provider).label
    session_id = make_session_id()
    now = utc_now_iso()
    record = add_session_record_version({
        "session_id": session_id,
        "title": (request.title or "").strip() or generated_session_title(
            request.specification,
            str(default_binding["model"]),
        ),
        "title_source": "user" if (request.title or "").strip() else "generated",
        "created_at_utc": now,
        "updated_at_utc": now,
        "provider": provider,
        "provider_label": provider_label,
        "model": default_binding["model"],
        "model_bindings": model_bindings,
        "runtime_harness_id": request.runtime_harness_id,
        "harness_definition_revision": spec.definition_revision,
        "runtime_harness_name": template.get("name", request.runtime_harness_id),
        "harness_runtime_config": workflow_runtime_config_from_effective(spec),
        "specification": request.specification,
        "job_ids": [],
        "chat_messages": [],
        "decision_comments": {},
    })
    record_path = session_record_path(session_id, sessions_dir=sessions_dir)
    record = validate_canonical_session_record(record)
    validate_canonical_session_record_context(
        record,
        record_path=record_path,
        sessions_dir=sessions_dir,
    )
    write_json_file(record_path, record)
    payload = session_payload_from_runs(record, [])
    return {"session": payload, "summary": summarize_session_payload(payload)}


def patch_modeling_session(
    session_id: str,
    request: SessionPatchRequest,
    *,
    sessions_dir: Path,
    runs_dir: Path,
) -> dict[str, Any]:
    def apply_patch(record: dict[str, Any]) -> None:
        if request.title is not None:
            title = request.title.strip()
            if not title:
                record["title"] = generated_session_title(
                    str(record.get("specification") or ""),
                    str(record.get("model") or ""),
                )
                record["title_source"] = "generated"
            else:
                record["title"] = title
                record["title_source"] = "user"
        if request.chat_message is not None:
            messages = record.get("chat_messages") if isinstance(record.get("chat_messages"), list) else []
            message = dict(request.chat_message)
            message.setdefault("id", f"msg-{len(messages) + 1:04d}")
            message.setdefault("created_at_utc", utc_now_iso())
            messages.append(message)
            record["chat_messages"] = messages
        if request.decision_comment is not None:
            patch_id = str(request.decision_comment.get("patch_id") or "").strip()
            text = str(request.decision_comment.get("text") or "").strip()
            if not patch_id:
                raise HTTPException(status_code=400, detail="decision_comment.patch_id is required.")
            comments = record.get("decision_comments") if isinstance(record.get("decision_comments"), dict) else {}
            comments[patch_id] = {"text": text, "updated_at_utc": utc_now_iso()}
            record["decision_comments"] = comments

    record = mutate_session_record(session_id, apply_patch, sessions_dir=sessions_dir)
    entries = session_run_records_by_session(runs_dir).get(session_id, [])
    payload = session_payload_from_runs(record, entries)
    return {"session": payload, "summary": summarize_session_payload(payload)}


def delete_modeling_session(session_id: str, *, sessions_dir: Path, runs_dir: Path) -> dict[str, Any]:
    record_path = session_record_path(session_id, sessions_dir=sessions_dir)
    initial_records = _strict_stored_run_records(runs_dir)
    initial_run_entries = [
        entry
        for entry in initial_records
        if str(entry[1].get("session_id") or "") == session_id
    ]
    initial_run_ids = {
        str(record.get("job_id") or run_dir.name)
        for run_dir, record in initial_run_entries
    }
    with run_locks(run_dir for run_dir, _record in initial_run_entries):
        with session_lock(record_path):
            read_session_record(session_id, sessions_dir=sessions_dir)
            all_records = _strict_stored_run_records(runs_dir)
            run_entries = [
                entry
                for entry in all_records
                if str(entry[1].get("session_id") or "") == session_id
            ]
            deleted_run_ids = {
                str(record.get("job_id") or run_dir.name)
                for run_dir, record in run_entries
            }
            if deleted_run_ids != initial_run_ids:
                raise HTTPException(
                    status_code=409,
                    detail="session_deletion_integrity_error",
                )
            for _surviving_dir, surviving_record in all_records:
                surviving_id = str(surviving_record.get("job_id") or "")
                if surviving_id in deleted_run_ids:
                    continue
                request = (
                    surviving_record.get("request")
                    if isinstance(surviving_record.get("request"), dict)
                    else {}
                )
                source_job_id = str(
                    request.get("resume_from_job_id") or ""
                ).strip()
                if (
                    source_job_id in deleted_run_ids
                    and request.get("resume_checkpoint_mode") in {None, ""}
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="resume_dependency_conflict",
                    )
            if any(
                run_status_is_active(record.get("status"))
                for _run_dir, record in run_entries
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Stop the active run before deleting this session.",
                )

            deleted_jobs = [
                str(record.get("job_id") or run_dir.name)
                for run_dir, record in run_entries
            ]
            session_dir = safe_session_dir(
                session_id,
                sessions_dir=sessions_dir,
            )
            try:
                for run_dir, _record in run_entries:
                    require_real_directory(run_dir, label="Run directory")
                    if first_unsafe_tree_entry(run_dir) is not None:
                        raise StoreTopologyError(
                            "Run directory contains an unsafe linked entry."
                        )
                if session_dir.exists():
                    require_real_directory(
                        session_dir,
                        label="Session directory",
                    )
                    if first_unsafe_tree_entry(session_dir) is not None:
                        raise StoreTopologyError(
                            "Session directory contains an unsafe linked entry."
                        )
            except StoreTopologyError as exc:
                raise HTTPException(
                    status_code=409,
                    detail="session_store_topology_error",
                ) from exc
            for run_dir, _record in run_entries:
                remove_verified_tree(run_dir)
            if session_dir.exists():
                remove_verified_tree(session_dir)
    return {"deleted": True, "session_id": session_id, "deleted_jobs": deleted_jobs}


__all__ = ["create_modeling_session", "delete_modeling_session", "patch_modeling_session"]
