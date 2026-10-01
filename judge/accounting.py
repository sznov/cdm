from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.artifacts import (
    load_json,
    normalize_checkpoint_manifest_rows,
    read_checkpoint_manifest_path,
    write_csv,
    write_json,
)


MODEL_CALL_FIELDS = [
    "call_id",
    "phase",
    "raw_kind",
    "spec_id",
    "generation_run_id",
    "checkpoint_label",
    "provider",
    "model",
    "harness_id",
    "template_id",
    "started_at_utc",
    "ended_at_utc",
    "duration_seconds",
    "status",
    "retry_index",
    "http_status_or_error",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
    "artifact_path",
]

RUN_SUMMARY_FIELDS = [
    "spec_id",
    "generation_run_id",
    "checkpoint_label",
    "provider",
    "model",
    "status",
    "model_call_count",
    "retry_count",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "correction_count",
    "operation_count",
    "run_dir",
]

PHASE_BY_KIND = {
    "direct_schema_baseline": "generation_direct_baseline",
    "async_op_patch_draft_model": "generation_draft",
    "structured_model_language_repair": "generation_language_repair",
    "structured_language_repair": "generation_language_repair",
    "async_op_patch_coverage_critic": "generation_coverage_critic",
    "async_op_patch_operations": "generation_patch_clerk",
    "freeform_correction_patch_operation": "generation_posthoc_correction",
}


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _usage_tokens(usage: Any) -> dict[str, int | str]:
    if not isinstance(usage, dict):
        return {"input_tokens": "", "output_tokens": "", "total_tokens": "", "cached_input_tokens": "", "reasoning_tokens": ""}
    prompt_details = usage.get("prompt_tokens_details") if isinstance(usage.get("prompt_tokens_details"), dict) else {}
    completion_details = usage.get("completion_tokens_details") if isinstance(usage.get("completion_tokens_details"), dict) else {}
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = _as_int(input_tokens) + _as_int(output_tokens)
    return {
        "input_tokens": _as_int(input_tokens) if input_tokens is not None else "",
        "output_tokens": _as_int(output_tokens) if output_tokens is not None else "",
        "total_tokens": _as_int(total_tokens) if total_tokens is not None else "",
        "cached_input_tokens": _as_int(prompt_details.get("cached_tokens", prompt_details.get("cached_input_tokens")))
        if prompt_details
        else "",
        "reasoning_tokens": _as_int(completion_details.get("reasoning_tokens")) if completion_details else "",
    }


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return load_json(path)
    except Exception:
        return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _model_call_rows_from_result(run_dir: Path, checkpoint: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = _load_json_if_exists(run_dir / "result.json")
    if not isinstance(result, dict):
        result = {}
    calls = result.get("model_call_logs")
    if not isinstance(calls, list):
        calls = []
    checkpoint = checkpoint or {}
    spec_id = str(checkpoint.get("spec_id") or run_dir.name).zfill(3)
    generation_run_id = str(checkpoint.get("generation_run_id") or run_dir.parent.name)
    checkpoint_label = str(checkpoint.get("checkpoint_label") or "final")
    rows: list[dict[str, Any]] = []
    for index, call in enumerate(calls, start=1):
        if not isinstance(call, dict):
            continue
        usage = _usage_tokens(call.get("usage"))
        raw_kind = str(call.get("kind") or "")
        rows.append(
            {
                "call_id": f"{generation_run_id}-{spec_id}-{index:04d}",
                "phase": PHASE_BY_KIND.get(raw_kind, raw_kind),
                "raw_kind": raw_kind,
                "spec_id": spec_id,
                "generation_run_id": generation_run_id,
                "checkpoint_label": checkpoint_label,
                "provider": checkpoint.get("provider", ""),
                "model": call.get("model") or checkpoint.get("model") or result.get("model", ""),
                "harness_id": checkpoint.get("harness_id", "gemma4-tuned-final"),
                "template_id": call.get("kind") or "",
                "started_at_utc": "",
                "ended_at_utc": "",
                "duration_seconds": "",
                "status": "failed" if call.get("error") else "completed",
                "retry_index": 0,
                "http_status_or_error": call.get("error") or "",
                **usage,
                "artifact_path": call.get("path") or "",
            }
        )
    return rows


def _trace_counts(run_dir: Path) -> dict[str, int]:
    events = _load_jsonl(run_dir / "trace.jsonl")
    correction_count = 0
    operation_count = 0
    for row in events:
        event = str(row.get("event") or "")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        lower_event = event.lower()
        text = json.dumps(payload, ensure_ascii=False).lower()
        if "correction" in lower_event or "posthoc" in text or "correction" in text:
            correction_count += 1
        operations = payload.get("operations")
        if isinstance(operations, list):
            operation_count += len(operations)
        elif payload.get("operation"):
            operation_count += 1
        elif "patch" in lower_event and ("operation" in text or "op" in text):
            operation_count += 1
    return {"correction_count": correction_count, "operation_count": operation_count}


def _sum_numeric(rows: list[dict[str, Any]], key: str) -> int:
    return sum(_as_int(row.get(key)) for row in rows if row.get(key) not in ("", None))


def generation_accounting_rows(
    run_root: Path,
    *,
    checkpoint_rows: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if checkpoint_rows is not None:
        checkpoints = normalize_checkpoint_manifest_rows(checkpoint_rows)
    else:
        manifest_path = run_root / "checkpoint_manifest.json"
        checkpoints = read_checkpoint_manifest_path(manifest_path) if manifest_path.exists() else []
    by_path = {str(Path(str(row.get("model_path") or "")).parent): row for row in checkpoints if row.get("model_path")}

    run_dirs = sorted({path.parent for path in run_root.rglob("result.json")})
    model_call_rows: list[dict[str, Any]] = []
    run_summary_rows: list[dict[str, Any]] = []
    for run_dir in run_dirs:
        rel_key = str(run_dir)
        checkpoint = by_path.get(rel_key) or by_path.get(str(run_dir.relative_to(run_root)).replace("\\", "/"), {})
        calls = _model_call_rows_from_result(run_dir, checkpoint)
        counts = _trace_counts(run_dir)
        model_call_rows.extend(calls)
        spec_id = str(checkpoint.get("spec_id") or run_dir.name).zfill(3)
        generation_run_id = str(checkpoint.get("generation_run_id") or run_dir.parent.name)
        run_summary_rows.append(
            {
                "spec_id": spec_id,
                "generation_run_id": generation_run_id,
                "checkpoint_label": checkpoint.get("checkpoint_label", "final"),
                "provider": checkpoint.get("provider", ""),
                "model": checkpoint.get("model", ""),
                "status": checkpoint.get("status", "generated" if (run_dir / "structured_model.json").exists() else "failed"),
                "model_call_count": len(calls),
                "retry_count": sum(1 for call in calls if _as_int(call.get("retry_index")) > 0),
                "input_tokens": _sum_numeric(calls, "input_tokens"),
                "output_tokens": _sum_numeric(calls, "output_tokens"),
                "total_tokens": _sum_numeric(calls, "total_tokens"),
                "correction_count": counts["correction_count"],
                "operation_count": counts["operation_count"],
                "run_dir": str(run_dir),
            }
        )
    return {"model_call_accounting": model_call_rows, "generation_run_summary": run_summary_rows}


def write_generation_accounting(run_root: Path, out_dir: Path) -> dict[str, list[dict[str, Any]]]:
    reports = generation_accounting_rows(run_root)
    write_json(out_dir / "model_call_accounting.json", reports["model_call_accounting"])
    write_json(out_dir / "generation_run_summary.json", reports["generation_run_summary"])
    write_csv(out_dir / "model_call_accounting.csv", reports["model_call_accounting"], MODEL_CALL_FIELDS)
    write_csv(out_dir / "generation_run_summary.csv", reports["generation_run_summary"], RUN_SUMMARY_FIELDS)
    return reports


__all__ = [
    "MODEL_CALL_FIELDS",
    "RUN_SUMMARY_FIELDS",
    "generation_accounting_rows",
    "write_generation_accounting",
]
