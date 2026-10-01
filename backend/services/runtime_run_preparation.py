from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.models import RunRequest
from backend.persistence.common import utc_now_iso
from backend.persistence.locks import run_lock
from backend.persistence.run_resume import run_resume_state
from backend.persistence.run_resume_materialization import (
    MATERIALIZED_RESUME_CHECKPOINT_REFERENCE,
    materialized_resume_checkpoint_bytes,
)
from backend.persistence.run_paths import safe_run_dir
from backend.persistence.run_sources import source_run_record
from backend.persistence.store_topology import first_unsafe_tree_entry, inspect_entry
from backend.persistence.run_record_integrity import RunRecordIntegrityError
from backend.persistence.session_records import read_session_record
from backend.services.prepared_run import PreparedRun
from backend.services.runtime_execution_snapshot import materialize_runtime_execution_snapshot
from backend.services.runtime_gemini_models import GEMINI_MODELS_CACHE_FILENAME
from backend.services.runtime_harness_spec import (
    materialized_runtime_harness_spec,
    workflow_runtime_override,
)
from backend.services.runtime_model_bindings import validate_runtime_harness_model_bindings
from backend.services.runtime_nvidia_nim_models import NVIDIA_NIM_CATALOG_CACHE_FILENAME
from harnesses.catalog import (
    HarnessDefinitionRevisionMismatchError,
    get_harness_definition,
)
from harnesses.provenance import load_recorded_protocol


def _supplied_fields(request: RunRequest) -> set[str]:
    return set(request.model_fields_set)


def _serialized_bindings(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        str(slot): (
            binding.model_dump(mode="json", exclude_unset=True)
            if hasattr(binding, "model_dump")
            else deepcopy(binding)
        )
        for slot, binding in value.items()
    }


def _session_record(session_id: str | None, sessions_dir: Path) -> dict[str, Any] | None:
    if not session_id:
        return None
    return read_session_record(session_id, sessions_dir=sessions_dir)


def _require_runnable_definition(runtime_harness_id: str):
    definition = get_harness_definition(runtime_harness_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Runtime harness not found.")
    if not definition.runnable:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Runtime harness '{runtime_harness_id}' is not available in the "
                "browser application. Use its script entry point instead."
            ),
        )
    return definition


def _prepare_fresh_run(
    request: RunRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    providers_dir: Path | None,
) -> PreparedRun:
    fields = _supplied_fields(request)
    session = _session_record(request.session_id, sessions_dir)
    session_harness_id = str(session.get("runtime_harness_id") or "") if session else ""
    runtime_harness_id = (
        request.runtime_harness_id
        if "runtime_harness_id" in fields
        else session_harness_id or request.runtime_harness_id
    )
    definition = _require_runnable_definition(runtime_harness_id)
    same_session_harness = bool(session and session_harness_id == runtime_harness_id)
    revision = (
        request.harness_definition_revision
        if "harness_definition_revision" in fields
        else (
            str(session.get("harness_definition_revision") or "") or None
            if same_session_harness
            else definition.definition_revision
        )
    )

    workflow_config: dict[str, Any] = {}
    if same_session_harness and isinstance(session.get("harness_runtime_config"), dict):
        try:
            workflow_config.update(workflow_runtime_override(session["harness_runtime_config"]))
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"The session's workflow configuration is invalid: {exc}",
            ) from exc
    workflow_config.update(workflow_runtime_override(request.harness_runtime_config))

    requested_bindings = _serialized_bindings(request.model_bindings)
    session_bindings = (
        deepcopy(session.get("model_bindings"))
        if same_session_harness and isinstance(session.get("model_bindings"), dict)
        else None
    )
    definition_bindings = definition.model_dump(mode="json").get("model_bindings") or definition.runtime_config.model_dump(
        mode="json"
    ).get("model_bindings")
    model_bindings = (
        requested_bindings
        if "model_bindings" in fields
        else session_bindings or definition_bindings
    )
    if not isinstance(model_bindings, dict):
        raise HTTPException(status_code=400, detail="Choose a model first.")
    model_bindings = validate_runtime_harness_model_bindings(
        runtime_harness_id,
        model_bindings,
    )

    specification = (
        request.specification
        if "specification" in fields and request.specification
        else str(session.get("specification") or "") if session else str(request.specification or "")
    )
    if not specification.strip():
        raise HTTPException(status_code=400, detail="Paste or load a specification first.")

    try:
        materialized = materialized_runtime_harness_spec(
            runtime_harness_id=runtime_harness_id,
            harness_definition_revision=revision,
            harness_runtime_config=workflow_config,
            model_bindings=model_bindings,
        )
        resolved_providers_dir = providers_dir or runs_dir.parent / "providers"
        execution = materialize_runtime_execution_snapshot(
            materialized,
            gemini_catalog_path=resolved_providers_dir / GEMINI_MODELS_CACHE_FILENAME,
            nvidia_catalog_path=resolved_providers_dir / NVIDIA_NIM_CATALOG_CACHE_FILENAME,
        )
    except HarnessDefinitionRevisionMismatchError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    template = definition.to_legacy_dict()
    return PreparedRun(
        effective_harness_run_spec=execution.spec,
        provider_execution=execution.provider,
        specification=specification,
        session_id=request.session_id,
        retry_of_job_id=request.retry_of_job_id,
        runtime_harness_name=definition.name,
        runtime_endpoint=definition.runtime_endpoint or "/api/runs",
        runtime_harness_snapshot=template,
    )


def _prepare_resumed_run(
    request: RunRequest,
    *,
    runs_dir: Path,
) -> PreparedRun:
    assert request.resume_from_job_id is not None
    fields = _supplied_fields(request)
    forbidden = fields.intersection(
        {"specification", "model_bindings", "harness_runtime_config"}
    )
    if forbidden:
        names = ", ".join(sorted(forbidden))
        raise HTTPException(
            status_code=409,
            detail=f"A resumed run cannot override its recorded protocol fields: {names}.",
        )

    source_dir = safe_run_dir(request.resume_from_job_id, runs_dir=runs_dir)
    with run_lock(source_dir):
        source_entry = inspect_entry(source_dir)
        if source_entry is None:
            raise HTTPException(status_code=404, detail="Source run not found.")
        if source_entry.is_reparse or not source_entry.is_directory:
            raise HTTPException(
                status_code=409,
                detail="run_store_topology_error",
            )
        if first_unsafe_tree_entry(source_dir) is not None:
            raise HTTPException(
                status_code=409,
                detail="run_store_topology_error",
            )
        try:
            source_dir, source_record = source_run_record(
                request.resume_from_job_id,
                runs_dir=runs_dir,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Source run not found.") from exc
        except RunRecordIntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="run_record_integrity_error",
            ) from exc
        try:
            recorded = load_recorded_protocol(source_dir)
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"The source run's recorded protocol is invalid: {exc}",
            ) from exc
        spec = recorded.effective_harness_run_spec
        if "runtime_harness_id" in fields and request.runtime_harness_id != spec.harness_id:
            raise HTTPException(
                status_code=409,
                detail="A resumed run must use the source run's harness definition.",
            )
        if (
            "harness_definition_revision" in fields
            and request.harness_definition_revision != spec.definition_revision
        ):
            raise HTTPException(
                status_code=409,
                detail="A resumed run must use the source run's harness definition revision.",
            )
        resume_state = run_resume_state(
            request.resume_from_job_id,
            effective_harness_run_spec=spec,
            trace_index=request.resume_trace_index,
            runs_dir=runs_dir,
        )
        checkpoint_payload = (
            deepcopy(resume_state.get("payload"))
            if isinstance(resume_state.get("payload"), dict)
            else {}
        )
        checkpoint_bytes = materialized_resume_checkpoint_bytes(
            source_job_id=request.resume_from_job_id,
            source_stage=str(resume_state.get("stage") or ""),
            source_trace_index=(
                int(resume_state["trace_index"])
                if isinstance(resume_state.get("trace_index"), int)
                and not isinstance(resume_state.get("trace_index"), bool)
                else request.resume_trace_index
            ),
            materialized_at_utc=utc_now_iso(),
            payload=checkpoint_payload,
        )
        resume_state = {
            **resume_state,
            "checkpoint_path": MATERIALIZED_RESUME_CHECKPOINT_REFERENCE,
        }
    runtime_harness = (
        deepcopy(source_record.get("agent_graph"))
        if isinstance(source_record.get("agent_graph"), dict)
        else {
            "id": spec.harness_id,
            "name": source_record.get("runtime_harness_name") or spec.harness_id,
            "definition_revision": spec.definition_revision,
            "runtime_endpoint": source_record.get("runtime_endpoint") or "/api/runs",
        }
    )
    runtime_name = str(
        source_record.get("runtime_harness_name")
        or runtime_harness.get("name")
        or spec.harness_id
    )
    runtime_endpoint = str(
        source_record.get("runtime_endpoint")
        or runtime_harness.get("runtime_endpoint")
        or "/api/runs"
    )
    return PreparedRun(
        effective_harness_run_spec=spec,
        provider_execution=recorded.provenance.provider,
        specification=recorded.specification,
        session_id=request.session_id or source_record.get("session_id"),
        retry_of_job_id=request.retry_of_job_id,
        resume_from_job_id=request.resume_from_job_id,
        resume_trace_index=request.resume_trace_index,
        resume_state=resume_state,
        resume_checkpoint_bytes=checkpoint_bytes,
        runtime_harness_name=runtime_name,
        runtime_endpoint=runtime_endpoint,
        runtime_harness_snapshot=runtime_harness,
    )


def prepare_run(
    request: RunRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    providers_dir: Path | None = None,
) -> PreparedRun:
    if request.resume_from_job_id:
        return _prepare_resumed_run(request, runs_dir=runs_dir)
    return _prepare_fresh_run(
        request,
        runs_dir=runs_dir,
        sessions_dir=sessions_dir,
        providers_dir=providers_dir,
    )


__all__ = ["prepare_run"]
