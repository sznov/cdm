from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.api.settings import (
    RUN_RECORD_FILENAME,
    RUN_SPECIFICATION_FILENAME,
    RUN_TRACE_FILENAME,
)
from backend.persistence.common import utc_now_iso, write_json_file
from backend.persistence.run_path_references import (
    RUN_RELATIVE_PATH_REFERENCE_MODE,
    run_relative_reference,
)
from backend.persistence.run_record_integrity import (
    validate_canonical_run_record,
    validate_canonical_run_record_context,
)
from backend.persistence.run_records import mutate_persisted_run_record
from backend.persistence.run_resume_materialization import (
    MATERIALIZED_RESUME_CHECKPOINT_MODE,
    MATERIALIZED_RESUME_CHECKPOINT_REFERENCE,
    checkpoint_sha256,
)
from backend.persistence.store_topology import ensure_real_directory_path
from backend.services.prepared_run import PreparedRun
from core.artifact_versions import add_run_record_version
from core.atomic_io import atomic_write_text, synchronized_mkdir
from core.job_ids import make_job_id
from core.model_bindings import normalize_model_bindings
from core.providers.factory import provider_descriptor
from harnesses.contracts import EffectiveHarnessRunSpec
from harnesses.provenance import ProviderExecutionIdentity, build_run_provenance


_MAX_GENERATED_RUN_ID_ATTEMPTS = 8


@dataclass(slots=True)
class RunStreamRecordContext:
    prepared_run: PreparedRun
    resolved_url: str
    resolved_provider: str
    job_id: str
    run_dir: Path
    model_call_log_dir: Path
    started_at_utc: str
    trace_path: Path
    record_path: Path
    run_record: dict[str, Any]
    sessions_dir: Path | None

    @property
    def effective_harness_run_spec(self) -> EffectiveHarnessRunSpec:
        return self.prepared_run.effective_harness_run_spec

    @property
    def provider_execution(self) -> ProviderExecutionIdentity:
        return self.prepared_run.provider_execution

    @property
    def resume_state(self) -> dict[str, Any] | None:
        return self.prepared_run.resume_state

    @property
    def runtime_harness(self) -> dict[str, Any]:
        return self.prepared_run.runtime_harness_snapshot


def _reserve_run_directory(
    runs_dir: Path,
    *,
    requested_job_id: str | None,
) -> tuple[str, Path]:
    ensure_real_directory_path(runs_dir)
    if requested_job_id is not None:
        run_dir = runs_dir / requested_job_id
        synchronized_mkdir(run_dir, exist_ok=False)
        return requested_job_id, run_dir

    for _attempt in range(_MAX_GENERATED_RUN_ID_ATTEMPTS):
        generated_job_id = make_job_id()
        run_dir = runs_dir / generated_job_id
        try:
            synchronized_mkdir(run_dir, exist_ok=False)
        except FileExistsError:
            continue
        return generated_job_id, run_dir
    raise FileExistsError(
        "Could not reserve a unique run directory after "
        f"{_MAX_GENERATED_RUN_ID_ATTEMPTS} attempts."
    )


def create_run_stream_record(
    prepared_run: PreparedRun,
    *,
    runs_dir: Path,
    sessions_dir: Path | None,
    initial_status: str = "running",
    job_id: str | None = None,
) -> RunStreamRecordContext:
    effective_spec = prepared_run.effective_harness_run_spec
    provider_execution = prepared_run.provider_execution
    effective_payload = effective_spec.model_dump(mode="json")
    model_bindings = normalize_model_bindings(effective_payload["model_bindings"])
    default_binding = model_bindings["default"]
    resolved_url = str(default_binding.get("base_url") or "")
    provider_id = str(default_binding["provider"])
    resolved_provider = provider_descriptor(provider_id).label
    job_id, run_dir = _reserve_run_directory(
        Path(runs_dir),
        requested_job_id=job_id or None,
    )
    model_call_log_dir = run_dir / "model_calls"
    started_at_utc = utc_now_iso()
    trace_path = run_dir / RUN_TRACE_FILENAME
    record_path = run_dir / RUN_RECORD_FILENAME
    provenance = build_run_provenance(
        spec=effective_spec,
        specification=prepared_run.specification,
        provider=provider_execution,
        whole_harness_max_attempts=1,
    )
    resume_state = prepared_run.resume_state
    resume_checkpoint_bytes = prepared_run.resume_checkpoint_bytes
    runtime_harness = prepared_run.runtime_harness_snapshot
    model_call_log_reference = run_relative_reference(run_dir, model_call_log_dir)
    # The specification is immutable and run.json is the publication commit
    # point.  Write it completely before publishing the canonical run record;
    # startup reconciliation removes an orphan directory after a crash.
    atomic_write_text(
        run_dir / RUN_SPECIFICATION_FILENAME,
        prepared_run.specification,
        encoding="utf-8",
    )
    if resume_checkpoint_bytes is not None:
        checkpoint_path = run_dir / MATERIALIZED_RESUME_CHECKPOINT_REFERENCE
        synchronized_mkdir(checkpoint_path.parent, exist_ok=False)
        atomic_write_text(
            checkpoint_path,
            resume_checkpoint_bytes.decode("utf-8"),
            encoding="utf-8",
        )
    request_payload: dict[str, Any] = {
        "session_id": prepared_run.session_id,
        "retry_of_job_id": prepared_run.retry_of_job_id,
        "specification_path": RUN_SPECIFICATION_FILENAME,
        "specification_sha256": prepared_run.specification_sha256,
        "specification_length": len(prepared_run.specification),
    }
    if prepared_run.resume_from_job_id:
        request_payload.update(
            resume_from_job_id=prepared_run.resume_from_job_id,
            resume_trace_index=prepared_run.resume_trace_index,
            resume_checkpoint_stage=(
                resume_state.get("stage") if resume_state else None
            ),
            resume_checkpoint_path=(
                MATERIALIZED_RESUME_CHECKPOINT_REFERENCE
                if resume_checkpoint_bytes is not None
                else resume_state.get("checkpoint_path") if resume_state else None
            ),
        )
        if resume_checkpoint_bytes is not None:
            request_payload.update(
                resume_checkpoint_mode=MATERIALIZED_RESUME_CHECKPOINT_MODE,
                resume_checkpoint_sha256=checkpoint_sha256(
                    resume_checkpoint_bytes
                ),
            )
    run_record: dict[str, Any] = add_run_record_version(
        {
            "job_id": job_id,
            "status": initial_status,
            "queued_at_utc": started_at_utc if initial_status == "queued" else None,
            "started_at_utc": None if initial_status == "queued" else started_at_utc,
            "completed_at_utc": None,
            "provider": provider_id,
            "provider_label": resolved_provider,
            "model": default_binding["model"],
            "model_bindings": model_bindings,
            "runtime_harness_id": effective_spec.harness_id,
            "harness_definition_revision": effective_spec.definition_revision,
            "effective_harness_run_spec": effective_payload,
            "provenance": provenance.model_dump(mode="json"),
            "runtime_harness_name": prepared_run.runtime_harness_name,
            "runtime_endpoint": prepared_run.runtime_endpoint,
            "session_id": prepared_run.session_id,
            "agent_graph": runtime_harness,
            "path_reference_mode": RUN_RELATIVE_PATH_REFERENCE_MODE,
            "model_call_log_dir": model_call_log_reference,
            "request": request_payload,
            "result": None,
            "error": None,
        }
    )
    run_record = validate_canonical_run_record(run_record)
    validate_canonical_run_record_context(
        run_record,
        record_path=record_path,
        runs_dir=runs_dir,
    )
    write_json_file(record_path, run_record)
    return RunStreamRecordContext(
        prepared_run=prepared_run,
        resolved_url=resolved_url,
        resolved_provider=resolved_provider,
        job_id=job_id,
        run_dir=run_dir,
        model_call_log_dir=model_call_log_dir,
        started_at_utc=started_at_utc,
        trace_path=trace_path,
        record_path=record_path,
        run_record=run_record,
        sessions_dir=sessions_dir,
    )


def mutate_run_stream_record(
    context: RunStreamRecordContext,
    mutation: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    context.run_record = mutate_persisted_run_record(context.record_path, mutation)
    return context.run_record


def update_run_stream_record(context: RunStreamRecordContext, **changes: Any) -> dict[str, Any]:
    def apply_changes(record: dict[str, Any]) -> None:
        record.update(changes)

    return mutate_run_stream_record(context, apply_changes)


def run_stream_start_payload(context: RunStreamRecordContext) -> dict[str, Any]:
    prepared = context.prepared_run
    resume_state = prepared.resume_state
    spec = prepared.effective_harness_run_spec
    config = spec.effective_config
    model_bindings = {
        slot: {
            key: value
            for key, value in binding.items()
            if key not in {"base_url", "gemini_base_url"}
        }
        for slot, binding in spec.model_dump(mode="json")["model_bindings"].items()
    }
    return {
        "provider": context.resolved_provider,
        "model": model_bindings["default"]["model"],
        "model_bindings": model_bindings,
        "job_id": context.job_id,
        "started_at_utc": context.started_at_utc,
        "runtime_harness_id": spec.harness_id,
        "harness_definition_revision": spec.definition_revision,
        "runtime_harness_name": prepared.runtime_harness_name,
        "model_call_log_dir": run_relative_reference(
            context.run_dir,
            context.model_call_log_dir,
        ),
        "endpoint_class": context.provider_execution.endpoint_class,
        "max_iterations": config.max_iterations,
        "batch_retries": config.batch_retries,
        "semantic_critic": config.semantic_critic,
        "infer_implicit_identifiers": config.infer_implicit_identifiers,
        "retry_of_job_id": prepared.retry_of_job_id,
        "resume_from_job_id": prepared.resume_from_job_id,
        "resume_trace_index": prepared.resume_trace_index,
        "resume_checkpoint_stage": resume_state.get("stage") if resume_state else None,
        "session_id": prepared.session_id,
    }


__all__ = [
    "RunStreamRecordContext",
    "create_run_stream_record",
    "mutate_run_stream_record",
    "run_stream_start_payload",
    "update_run_stream_record",
]
