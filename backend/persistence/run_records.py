from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.api.settings import STRUCTURED_PATCH_HARNESS_IDS
from backend.persistence.common import read_json_file, write_json_file
from backend.persistence.locks import run_lock
from backend.persistence.post_run_transaction_guard import (
    require_post_run_mutation_allowed,
)
from backend.persistence.result_records import read_result_record
from backend.persistence.run_record_integrity import (
    RunRecordIntegrityError,
    read_canonical_run_record,
    validate_canonical_run_record,
)
from backend.persistence.run_harness import inferred_runtime_harness_id, inferred_runtime_harness_name
from backend.persistence.run_resume import latest_async_op_patch_resume_checkpoint
from backend.persistence.run_trace import TraceFormatError
from core.plantuml_structured import render_structured_model_to_plantuml
from core.schemas import StructuredModel


def summarize_run_record(
    record: dict[str, Any],
    *,
    run_dir: Path | None = None,
    trace_event_count: int | None = None,
) -> dict[str, Any]:
    record = validate_canonical_run_record(record)
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    runtime_harness_id = inferred_runtime_harness_id(record)
    resume_checkpoint = None
    if run_dir is not None and runtime_harness_id in STRUCTURED_PATCH_HARNESS_IDS:
        try:
            resume_checkpoint = latest_async_op_patch_resume_checkpoint(run_dir, record)
        except (OSError, TraceFormatError):
            # Trace availability is reported independently by the query layer;
            # a damaged trace must not prevent the remaining valid runs from
            # appearing in the list.
            resume_checkpoint = None

    def first_present(*values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None

    summary = {
        "schema_version": record.get("schema_version"),
        "artifact_kind": record.get("artifact_kind"),
        "job_id": record.get("job_id"),
        "status": record.get("status", "unknown"),
        "started_at_utc": record.get("started_at_utc"),
        "completed_at_utc": record.get("completed_at_utc"),
        "provider": record.get("provider"),
        "provider_label": record.get("provider_label"),
        "model": record.get("model"),
        "model_bindings": record.get("model_bindings") if isinstance(record.get("model_bindings"), dict) else None,
        "runtime_harness_id": runtime_harness_id,
        "harness_definition_revision": record.get("harness_definition_revision"),
        "runtime_harness_name": inferred_runtime_harness_name(record),
        "resume_checkpoint_stage": resume_checkpoint.get("stage") if resume_checkpoint else None,
        "resumable": resume_checkpoint is not None,
        "stop_reason": first_present(result.get("stop_reason"), record.get("stop_reason")),
        "iterations": first_present(result.get("iterations"), record.get("iterations")),
        "accepted_operation_count": first_present(
            result.get("accepted_operation_count"),
            record.get("accepted_operation_count"),
        ),
        "rejected_operation_count": first_present(
            result.get("rejected_operation_count"),
            record.get("rejected_operation_count"),
        ),
    }
    if trace_event_count is not None:
        summary["trace_event_count"] = trace_event_count
    return summary


def refresh_archived_plantuml_payloads(run_dir: Path, record: dict[str, Any], trace: list[dict[str, Any]]) -> None:
    structured_model_path = run_dir / "structured_model.json"
    plantuml = ""
    if structured_model_path.is_file():
        try:
            model = StructuredModel.model_validate(json.loads(structured_model_path.read_text(encoding="utf-8")))
            plantuml = render_structured_model_to_plantuml(model)
        except Exception:
            plantuml = ""

    if plantuml:
        result = record.get("result")
        if isinstance(result, dict):
            result["plantuml"] = plantuml

    for entry in trace:
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        structured_payload = payload.get("structured_model")
        if isinstance(structured_payload, dict):
            try:
                event_model = StructuredModel.model_validate(structured_payload)
                event_plantuml = render_structured_model_to_plantuml(event_model)
            except Exception:
                event_plantuml = ""
            if event_plantuml:
                payload["plantuml"] = event_plantuml
                continue
        if plantuml and entry.get("event") in {"plantuml_preview", "done"} and ("plantuml" in payload or "plantuml_url" in payload):
            payload["plantuml"] = plantuml


def run_payload_with_final_result(record: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    run_payload = validate_canonical_run_record(record)
    result_path = run_dir / "result.json"
    if result_path.is_file():
        try:
            result_payload = read_result_record(run_dir)
        except (OSError, json.JSONDecodeError):
            result_payload = None
        if isinstance(result_payload, dict):
            existing_result = run_payload.get("result") if isinstance(run_payload.get("result"), dict) else {}
            run_payload["result"] = {**existing_result, **summarize_run_record(record, run_dir=run_dir), **result_payload}
    return run_payload


def mutate_persisted_run_record(
    record_path: Path,
    mutation: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Reload and mutate a run record within one run-directory transaction."""

    with run_lock(record_path.parent):
        require_post_run_mutation_allowed(record_path.parent)
        record = read_canonical_run_record(
            record_path,
            runs_dir=record_path.parent.parent,
        )
        mutation(record)
        record = validate_canonical_run_record(record)
        write_json_file(record_path, record)
        return record


def update_persisted_run_record(record_path: Path, **changes: Any) -> dict[str, Any]:
    def apply_changes(record: dict[str, Any]) -> None:
        record.update(changes)

    return mutate_persisted_run_record(record_path, apply_changes)


__all__ = [
    "RunRecordIntegrityError",
    "mutate_persisted_run_record",
    "refresh_archived_plantuml_payloads",
    "run_payload_with_final_result",
    "summarize_run_record",
    "update_persisted_run_record",
]
