from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.artifacts import utc_now, write_checkpoint_manifest, write_json, write_profile_manifest, write_timing_csv
from core.config_safety import redact_persisted_value, safe_exception_detail
from core.job_ids import make_job_id
from core.model_bindings import normalize_model_bindings
from core.model_client import TextModelClient
from core.operation_loop_result import OperationLoopResult, write_result
from core.providers.factory import build_text_model_client, default_model_for_provider
from harnesses.contracts import CorrectionSequenceSummary, HarnessCheckpointRow
from harnesses.catalog import materialize_harness_run_spec
from harnesses.execution import HarnessExecutionRequest, execute_materialized_harness
from harnesses.provenance import harness_run_artifact, materialize_script_execution
from harnesses.structured_patch.required_correction_phase import (
    RequiredCorrectionPhaseError,
)


DEFAULT_STRUCTURED_PATCH_HARNESS_ID = "gemma4-tuned-final"


@dataclass(slots=True)
class StructuredPatchHarnessRun:
    result: OperationLoopResult
    correction_sequence: dict[str, Any] | None = None


def selected_spec_paths(spec_dir: Path, spec_ids: list[str]) -> list[Path]:
    if spec_ids:
        return [spec_dir / f"{str(spec_id).zfill(3)}.txt" for spec_id in spec_ids]
    return sorted(spec_dir.glob("*.txt"))


def reference_path_for(reference_dir: Path | None, spec_id: str) -> str:
    if reference_dir is None:
        return ""
    candidates = [
        reference_dir / spec_id / "structured_model.json",
        reference_dir / f"{spec_id}.json",
        reference_dir / f"{spec_id}.structured_model.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def checkpoint_row_for(
    *,
    spec_id: str,
    generation_id: str,
    spec_path: Path,
    job_dir: Path,
    reference_model_path: str,
    provider: str,
    model: str,
    harness_id: str,
    status: str,
    correction_sequence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "spec_id": spec_id,
        "generation_run_id": generation_id,
        "checkpoint_label": "final",
        "spec_path": str(spec_path),
        "reference_model_path": reference_model_path,
        "gold_path": reference_model_path,
        "model_path": str(job_dir / "structured_model.json"),
        "plantuml_path": str(job_dir / "final.plantuml"),
        "plantuml_url": "",
        "provider": provider,
        "model": model,
        "harness_id": harness_id,
        "status": status,
    }
    if correction_sequence is not None:
        summary = CorrectionSequenceSummary(
            template_id=str(correction_sequence.get("template_id") or ""),
            changed_count=int(correction_sequence.get("changed_count", 0)),
            accepted_count=int(correction_sequence.get("accepted_count", 0)),
            rejected_count=int(correction_sequence.get("rejected_count", 0)),
            deferred_count=int(correction_sequence.get("deferred_count", 0)),
            checkpoint_stage=str(correction_sequence.get("checkpoint_stage") or ""),
        )
        # The richer typed value validates the producer boundary. Keep the
        # established three-field manifest shape for existing research tools.
        row["correction_sequence"] = {
            "template_id": summary.template_id,
            "changed_count": summary.changed_count,
            "checkpoint_stage": summary.checkpoint_stage,
        }
    return HarnessCheckpointRow.model_validate(row).detached_dict()


def write_trace_event(trace_path: Path, event: str, payload: dict[str, Any]) -> None:
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    safe_payload = redact_persisted_value(payload)
    with trace_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {"timestamp_utc": utc_now(), "event": event, "payload": safe_payload},
                ensure_ascii=False,
            )
            + "\n"
        )


async def run_structured_patch_harness(
    *,
    specification: str,
    client: TextModelClient,
    harness_id: str = DEFAULT_STRUCTURED_PATCH_HARNESS_ID,
    max_attempts: int | None = None,
    infer_implicit_identifiers: bool | None = None,
    structured_language_repair: bool | None = None,
    direct_microop_judge: bool = False,
    auto_correction_sequence: bool | None = None,
    correction_template_id: str | None = None,
    max_correction_operations: int | None = None,
    job_id: str | None = None,
    model_call_log_dir: Path | None = None,
    resume_state: dict[str, Any] | None = None,
    on_event: Any | None = None,
) -> StructuredPatchHarnessRun:
    runtime_config_override: dict[str, Any] = {
        "direct_microop_judge": bool(direct_microop_judge),
    }
    optional_overrides = {
        "max_attempts": max_attempts,
        "infer_implicit_identifiers": infer_implicit_identifiers,
        "language_repair": structured_language_repair,
        "auto_correction_sequence": auto_correction_sequence,
        "correction_template_id": correction_template_id,
        "max_correction_operations": max_correction_operations,
    }
    runtime_config_override.update(
        {key: value for key, value in optional_overrides.items() if value is not None}
    )
    spec = materialize_harness_run_spec(
        harness_id,
        runtime_config_override=runtime_config_override,
    )
    execution = await execute_materialized_harness(
        HarnessExecutionRequest(
            spec=spec,
            specification=specification,
            client=client,
            job_id=job_id or make_job_id(),
            model_call_log_dir=model_call_log_dir,
            resume_state=resume_state,
            on_event=on_event,
        )
    )
    return StructuredPatchHarnessRun(
        result=execution.result,
        correction_sequence=execution.correction_sequence,
    )


async def generate_one(
    *,
    spec_path: Path,
    out_dir: Path,
    generation_id: str,
    provider: str,
    model: str,
    base_url: str | None,
    timeout_seconds: float,
    max_attempts: int,
    reference_dir: Path | None,
    resume: bool,
    harness_id: str = DEFAULT_STRUCTURED_PATCH_HARNESS_ID,
    auto_correction_sequence: bool | None = None,
    correction_template_id: str | None = None,
    max_completion_tokens: int | None = None,
) -> dict[str, Any]:
    spec_id = spec_path.stem.zfill(3)
    job_dir = out_dir / "harness_runs" / generation_id / spec_id
    model_call_log_dir = job_dir / "model_calls"
    reference_model_path = reference_path_for(reference_dir, spec_id)
    timing = {
        "phase": "generate",
        "step": "batch_harness_generate",
        "key": f"{generation_id}-{spec_id}",
        "started_at_utc": utc_now(),
        "command": "python -m scripts.generation.batch_harness",
        "returncode": 1,
        "status": "failed",
    }
    start = time.monotonic()

    if resume and (job_dir / "structured_model.json").exists():
        timing["status"] = "skipped"
        timing["returncode"] = 0
        timing["duration_seconds"] = 0.0
        correction_meta = None
        marker_path = job_dir / "correction_sequence.json"
        if marker_path.exists():
            try:
                correction_meta = json.loads(marker_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                correction_meta = None
        row = checkpoint_row_for(
            spec_id=spec_id,
            generation_id=generation_id,
            spec_path=spec_path,
            job_dir=job_dir,
            reference_model_path=reference_model_path,
            provider=provider,
            model=model,
            harness_id=harness_id,
            status="generated",
            correction_sequence=correction_meta if isinstance(correction_meta, dict) else None,
        )
        return {"row": row, "timing": timing, "attempts": 0, "job_dir": str(job_dir)}

    job_dir.mkdir(parents=True, exist_ok=True)
    trace_path = job_dir / "trace.jsonl"
    if trace_path.exists():
        trace_path.unlink()
    outer_attempts = max(1, int(max_attempts or 1))
    specification = spec_path.read_text(encoding="utf-8")
    binding_override: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "timeout_seconds": timeout_seconds,
    }
    if max_completion_tokens is not None:
        binding_override["max_completion_tokens"] = max_completion_tokens
    if base_url is not None:
        binding_override["base_url"] = base_url
    resolved_bindings = normalize_model_bindings({"default": binding_override})
    resolved_binding = resolved_bindings["default"]
    runtime_config_override: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "timeout_seconds": timeout_seconds,
    }
    if provider == "gemini":
        runtime_config_override["gemini_base_url"] = resolved_binding["base_url"]
    if auto_correction_sequence is not None:
        runtime_config_override["auto_correction_sequence"] = auto_correction_sequence
    if correction_template_id is not None:
        runtime_config_override["correction_template_id"] = (
            correction_template_id
        )
    harness_run_spec = materialize_harness_run_spec(
        harness_id,
        runtime_config_override=runtime_config_override,
        model_bindings=resolved_bindings,
    )
    harness_run_spec, provider_execution = materialize_script_execution(harness_run_spec)
    harness_run_spec_path = job_dir / "harness_run_spec.json"
    write_json(
        harness_run_spec_path,
        harness_run_artifact(
            spec=harness_run_spec,
            specification=specification,
            provider=provider_execution,
            whole_harness_max_attempts=outer_attempts,
        ).model_dump(mode="json"),
    )
    materialized_binding = normalize_model_bindings(
        harness_run_spec.model_dump(mode="json")["model_bindings"]
    )["default"]
    client = build_text_model_client(
        provider=str(materialized_binding["provider"]),
        model=str(materialized_binding["model"]),
        base_url=materialized_binding.get("base_url"),
        timeout_seconds=float(materialized_binding["timeout_seconds"]),
        max_completion_tokens=materialized_binding.get("max_completion_tokens"),
        reasoning_effort=materialized_binding.get("reasoning_effort"),
        temperature=materialized_binding.get("temperature"),
        top_p=materialized_binding.get("top_p"),
        provider_options={
            **dict(materialized_binding.get("provider_options") or {}),
            **(
                {"catalog_entries": provider_execution.execution_catalog_entries()}
                if provider_execution.execution_catalog_entries() is not None
                else {}
            ),
        },
        model_parameters=materialized_binding.get("model_parameters"),
        response_format_json_object=True,
    )

    async def on_event(event: str, payload: dict[str, Any]) -> None:
        write_trace_event(trace_path, event, payload)

    attempt_records: list[dict[str, Any]] = []
    last_error: BaseException | None = None
    for attempt_index in range(1, outer_attempts + 1):
        attempt_started = utc_now()
        if trace_path.exists():
            trace_path.unlink()
        try:
            execution = await execute_materialized_harness(
                HarnessExecutionRequest(
                    spec=harness_run_spec,
                    specification=specification,
                    client=client,
                    job_id=f"{generation_id}-{spec_id}",
                    model_call_log_dir=model_call_log_dir,
                    on_event=on_event,
                )
            )
            write_result(execution.result, job_dir)
            if execution.correction_sequence is not None:
                write_json(
                    job_dir / "correction_sequence.json",
                    redact_persisted_value(execution.correction_sequence),
                )
            row = checkpoint_row_for(
                spec_id=spec_id,
                generation_id=generation_id,
                spec_path=spec_path,
                job_dir=job_dir,
                reference_model_path=reference_model_path,
                provider=provider,
                model=execution.result.model or model,
                harness_id=harness_id,
                status="generated",
                correction_sequence=execution.correction_sequence,
            )
            timing["status"] = "completed"
            timing["returncode"] = 0
            timing["attempts"] = attempt_index
            attempt_records.append(
                {
                    "attempt": attempt_index,
                    "status": "completed",
                    "started_at_utc": attempt_started,
                    "ended_at_utc": utc_now(),
                }
            )
            timing["duration_seconds"] = round(time.monotonic() - start, 3)
            return {
                "row": row,
                "timing": timing,
                "attempts": attempt_index,
                "attempt_records": attempt_records,
                "job_dir": str(job_dir),
                "harness_run_spec_path": str(harness_run_spec_path),
                "whole_harness_max_attempts": outer_attempts,
            }
        except Exception as exc:
            last_error = exc
            safe_error = safe_exception_detail(exc)
            attempt_records.append(
                {
                    "attempt": attempt_index,
                    "status": "failed",
                    "started_at_utc": attempt_started,
                    "ended_at_utc": utc_now(),
                    "error": safe_error,
                    "type": type(exc).__name__,
                    "will_retry": attempt_index < outer_attempts,
                }
            )

    error_text = (
        safe_exception_detail(last_error)
        if last_error is not None
        else "Generation failed."
    )
    error_type = type(last_error).__name__ if last_error is not None else "RuntimeError"
    write_json(
        job_dir / "error.json",
        {
            "error": error_text,
            "type": error_type,
            "timestamp_utc": utc_now(),
            "attempts": attempt_records,
        },
    )
    row = checkpoint_row_for(
        spec_id=spec_id,
        generation_id=generation_id,
        spec_path=spec_path,
        job_dir=job_dir,
        reference_model_path=reference_model_path,
        provider=provider,
        model=model,
        harness_id=harness_id,
        status="failed",
    )
    row["error"] = error_text
    timing["attempts"] = len(attempt_records)
    timing["duration_seconds"] = round(time.monotonic() - start, 3)
    return {
        "row": row,
        "timing": timing,
        "attempts": len(attempt_records),
        "attempt_records": attempt_records,
        "job_dir": str(job_dir),
        "harness_run_spec_path": str(harness_run_spec_path),
        "whole_harness_max_attempts": outer_attempts,
        "error": error_text,
    }


async def run_structured_patch_batch(
    *,
    spec_dir: Path,
    out_dir: Path,
    reference_dir: Path | None,
    spec_ids: list[str],
    generation_repeats: int,
    concurrency: int,
    resume: bool,
    max_attempts: int,
    profile: str,
    provider: str,
    model: str | None,
    base_url: str | None,
    timeout_seconds: float,
    max_completion_tokens: int | None = None,
    harness_id: str = DEFAULT_STRUCTURED_PATCH_HARNESS_ID,
    auto_correction_sequence: bool | None = None,
    correction_template_id: str | None = None,
) -> int:
    if provider not in {"gemini", "nvidia_nim"}:
        raise ValueError("Structured-patch harness generation currently supports provider='gemini' or provider='nvidia_nim'.")
    out_dir.mkdir(parents=True, exist_ok=True)
    resolved_model = model or default_model_for_provider(provider)
    write_profile_manifest(
        out_dir,
        {
            "profile": profile,
            "provider": provider,
            "model": resolved_model,
            "harness_id": harness_id,
            "spec_dir": str(spec_dir),
            "reference_dir": str(reference_dir) if reference_dir else "",
            "generation_repeats": generation_repeats,
            "concurrency": concurrency,
            "resume": bool(resume),
            "whole_harness_max_attempts": max(1, int(max_attempts or 1)),
            "created_by": "python -m scripts.generation.batch_harness",
        },
    )
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def generate_bounded(spec_path: Path, generation_id: str) -> dict[str, Any]:
        async with semaphore:
            return await generate_one(
                spec_path=spec_path,
                out_dir=out_dir,
                generation_id=generation_id,
                provider=provider,
                model=resolved_model,
                base_url=base_url.rstrip("/") if base_url else None,
                timeout_seconds=timeout_seconds,
                max_completion_tokens=max_completion_tokens,
                max_attempts=max_attempts,
                reference_dir=reference_dir,
                resume=resume,
                harness_id=harness_id,
                auto_correction_sequence=auto_correction_sequence,
                correction_template_id=correction_template_id,
            )

    tasks = [
        generate_bounded(spec_path, f"gen-{repeat:03d}")
        for repeat in range(1, generation_repeats + 1)
        for spec_path in selected_spec_paths(spec_dir, spec_ids)
    ]
    results = await asyncio.gather(*tasks)
    rows = [result["row"] for result in results if isinstance(result.get("row"), dict)]
    timing_rows = [result["timing"] for result in results if isinstance(result.get("timing"), dict)]
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    write_checkpoint_manifest(out_dir, rows)
    write_json(out_dir / "run_timing.json", timing_rows)
    write_timing_csv(out_dir)
    write_json(
        out_dir / "batch_manifest.json",
        {
            "created_at_utc": utc_now(),
            "profile": profile,
            "provider": provider,
            "model": resolved_model,
            "harness_id": harness_id,
            "whole_harness_max_attempts": max(1, int(max_attempts or 1)),
            "status_counts": status_counts,
            "runs": results,
        },
    )
    return 0 if not any(row.get("status") == "failed" for row in rows) else 1


__all__ = [
    "DEFAULT_STRUCTURED_PATCH_HARNESS_ID",
    "RequiredCorrectionPhaseError",
    "StructuredPatchHarnessRun",
    "checkpoint_row_for",
    "generate_one",
    "reference_path_for",
    "run_structured_patch_batch",
    "run_structured_patch_harness",
    "selected_spec_paths",
]
