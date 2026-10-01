from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.api.settings import RUN_TRACE_FILENAME
from backend.persistence.run_resume_checkpoints import RESUMABLE_ASYNC_OP_PATCH_STAGES
from backend.persistence.run_trace import load_trace
from core.schemas import StructuredModel


def latest_trace_resume_checkpoint(
    run_dir: Path,
    record: dict[str, Any] | None = None,
    *,
    max_trace_index: int | None = None,
) -> dict[str, Any] | None:
    trace_path = run_dir / RUN_TRACE_FILENAME
    if not trace_path.is_file():
        return None
    trace = load_trace(trace_path)
    latest_model: dict[str, Any] | None = None
    latest_stage = ""
    latest_order = 0
    latest_timestamp = ""
    draft_model_issues: list[dict[str, Any]] = []
    draft_issue_decision_patches: list[dict[str, Any]] = []
    draft_issue_hard_findings: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    decision_patches: list[dict[str, Any]] = []

    def remember_model(payload: dict[str, Any], stage: str, timestamp: str) -> None:
        nonlocal latest_model, latest_stage, latest_order, latest_timestamp
        model_payload = payload.get("structured_model")
        if not isinstance(model_payload, dict):
            return
        try:
            model = StructuredModel.model_validate(model_payload)
        except Exception:
            return
        order = RESUMABLE_ASYNC_OP_PATCH_STAGES.get(stage, 0)
        if order >= latest_order:
            latest_model = model.model_dump(mode="json")
            latest_stage = stage
            latest_order = order
            latest_timestamp = timestamp

    for trace_index, entry in enumerate(trace):
        if max_trace_index is not None and trace_index > max_trace_index:
            break
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        event = str(entry.get("event") or "")
        timestamp = str(entry.get("timestamp_utc") or "")
        if event == "draft_model_validation" and payload.get("accepted") is True:
            remember_model(payload, "async-op-patch-after-draft", timestamp)
        elif event == "draft_model_issues":
            if isinstance(payload.get("issues"), list):
                draft_model_issues = [item for item in payload["issues"] if isinstance(item, dict)]
            if isinstance(payload.get("decision_patches"), list):
                draft_issue_decision_patches = [item for item in payload["decision_patches"] if isinstance(item, dict)]
            if isinstance(payload.get("hard_findings"), list):
                draft_issue_hard_findings = [item for item in payload["hard_findings"] if isinstance(item, dict)]
        elif event == "plan_coverage_critic_result":
            if isinstance(payload.get("findings"), list):
                findings = [item for item in payload["findings"] if isinstance(item, dict)]
            if latest_model is not None:
                latest_stage = "async-op-patch-after-coverage-critic"
                latest_order = RESUMABLE_ASYNC_OP_PATCH_STAGES[latest_stage]
                latest_timestamp = timestamp or latest_timestamp
        elif event == "resume_from_checkpoint":
            stage = str(payload.get("stage") or "")
            if stage in RESUMABLE_ASYNC_OP_PATCH_STAGES:
                remember_model(payload, stage, timestamp)
            if isinstance(payload.get("findings"), list):
                findings = [item for item in payload["findings"] if isinstance(item, dict)]
            if isinstance(payload.get("decision_patches"), list):
                decision_patches = [item for item in payload["decision_patches"] if isinstance(item, dict)]
        elif event == "decision_patches" and isinstance(payload.get("decision_patches"), list):
            decision_patches = [item for item in payload["decision_patches"] if isinstance(item, dict)]
        elif event == "partial_model_snapshot":
            stage = (
                "async-op-patch-after-patch-operations"
                if isinstance(payload.get("op_result"), dict)
                else "async-op-patch-after-language-repair"
            )
            remember_model(payload, stage, timestamp)
        elif event == "structured_model_validated":
            remember_model(payload, "async-op-patch-after-patch-operations", timestamp)

    if latest_model is None or not latest_stage:
        return None
    fallback_timestamp = ""
    if isinstance(record, dict):
        fallback_timestamp = str(record.get("completed_at_utc") or record.get("started_at_utc") or "")
    payload: dict[str, Any] = {
        "structured_model": latest_model,
        "draft_model_issues": draft_model_issues,
        "draft_issue_decision_patches": draft_issue_decision_patches,
        "draft_issue_hard_findings": draft_issue_hard_findings,
        "findings": findings,
        "decision_patches": decision_patches,
    }
    return {
        "stage": latest_stage,
        "timestamp_utc": latest_timestamp or fallback_timestamp,
        "payload": payload,
        "path": str(trace_path),
        "order": latest_order,
        "legacy_trace_fallback": True,
        "trace_index": max_trace_index,
    }


__all__ = ["latest_trace_resume_checkpoint"]
