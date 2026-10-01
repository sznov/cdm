from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.artifacts import append_timing, write_checkpoint_manifest, write_json, write_profile_manifest, utc_now
from core.config_safety import redact_persisted_value, redact_sensitive_text, safe_exception_detail
from core.model_call_completion import complete_with_logging
from core.model_call_logger import ModelCallLogger
from core.model_bindings import normalize_model_bindings
from core.model_client import completion_result_payload
from core.plantuml_structured import render_structured_model_to_plantuml
from core.providers.factory import build_text_model_client, default_model_for_provider
from core.refill import collect_valid_attempts
from harnesses.catalog import materialize_harness_run_spec
from harnesses.direct_baseline.prompt_profiles import (
    DirectPromptProfile,
    build_direct_user_prompt,
    direct_prompt_profile,
)
from harnesses.structured_patch.model_parsing import parse_structured_model_output
from harnesses.provenance import harness_run_artifact, materialize_script_execution


DIRECT_PROMPT_HARNESS_IDS = {
    "schema_only_v1": "direct-baseline-schema-only-v1",
    "structured_draft_with_issues": "direct-baseline-structured-draft-with-issues",
}


def selected_spec_paths(spec_dir: Path, spec_ids: list[str]) -> list[Path]:
    if spec_ids:
        return [spec_dir / f"{str(spec_id).zfill(3)}.txt" for spec_id in spec_ids]
    return sorted(spec_dir.glob("*.txt"))


def reference_path_for(reference_dir: Path | None, spec_id: str) -> str:
    if reference_dir is None:
        return ""
    for candidate in (
        reference_dir / spec_id / "structured_model.json",
        reference_dir / f"{spec_id}.json",
        reference_dir / f"{spec_id}.structured_model.json",
    ):
        if candidate.exists():
            return str(candidate)
    return ""


async def generate_direct_baseline_attempt(
    *,
    spec_path: Path,
    out_dir: Path,
    generation_id: str,
    attempt_id: str | None,
    provider: str,
    model: str,
    base_url: str | None,
    timeout_seconds: float,
    max_completion_tokens: int | None,
    codex_reasoning_effort: str | None,
    prompt_profile: DirectPromptProfile,
    reference_dir: Path | None = None,
) -> dict[str, Any]:
    spec_id = spec_path.stem.zfill(3)
    attempt_id = attempt_id or generation_id
    job_dir = out_dir / "direct_runs" / generation_id / spec_id / attempt_id
    job_dir.mkdir(parents=True, exist_ok=True)
    specification = spec_path.read_text(encoding="utf-8")
    binding_override: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "timeout_seconds": timeout_seconds,
        "max_completion_tokens": max_completion_tokens,
        "reasoning_effort": codex_reasoning_effort if provider == "codex" else None,
    }
    if base_url is not None:
        binding_override["base_url"] = base_url
    bindings = normalize_model_bindings({"default": binding_override})
    materialized_spec = materialize_harness_run_spec(
        DIRECT_PROMPT_HARNESS_IDS[prompt_profile.id],
        runtime_config_override={
            "provider": provider,
            "model": model,
            "prompt_profile": prompt_profile.id,
            "batch_retries": 1,
            "timeout_seconds": timeout_seconds,
        },
        model_bindings=bindings,
    )
    materialized_spec, provider_execution = materialize_script_execution(materialized_spec)
    write_json(
        job_dir / "harness_run_spec.json",
        harness_run_artifact(
            spec=materialized_spec,
            specification=specification,
            provider=provider_execution,
            whole_harness_max_attempts=1,
        ).model_dump(mode="json"),
    )
    materialized_binding = materialized_spec.model_dump(mode="json")["model_bindings"]["default"]
    logger = ModelCallLogger(job_id=f"{generation_id}-{spec_id}-{attempt_id}", log_dir=job_dir / "model_calls")
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
    user_content = build_direct_user_prompt(specification=specification, prompt_profile=prompt_profile)
    completion, _log = await complete_with_logging(
        client=client,
        logger=logger,
        kind="direct_schema_baseline",
        system_prompt=prompt_profile.system_prompt,
        user_content=user_content,
    )
    structured_model = parse_structured_model_output(completion.text, repair_missing_endpoint_entities=True)
    plantuml = render_structured_model_to_plantuml(structured_model)
    reference_model_path = reference_path_for(reference_dir, spec_id)
    write_json(
        job_dir / "structured_model.json",
        redact_persisted_value(structured_model.model_dump(mode="json")),
    )
    (job_dir / "model.plantuml").write_text(
        redact_sensitive_text(
            plantuml,
            redact_named_values=False,
            redact_url_fragments=False,
        ),
        encoding="utf-8",
    )
    write_json(
        job_dir / "raw_completion.json",
        redact_persisted_value(completion_result_payload(completion)),
    )
    return {
        "spec_id": spec_id,
        "generation_run_id": generation_id,
        "attempt_id": attempt_id,
        "checkpoint_label": "single_shot_schema",
        "spec_path": str(spec_path),
        "reference_model_path": reference_model_path,
        "gold_path": reference_model_path,
        "model_path": str(job_dir / "structured_model.json"),
        "plantuml_path": str(job_dir / "model.plantuml"),
        "plantuml_url": "",
        "provider": provider,
        "model": completion.model or model,
        "harness_run_spec_path": str(job_dir / "harness_run_spec.json"),
        "status": "generated",
    }


async def run_direct_baseline_generation(
    *,
    spec_dir: Path,
    out_dir: Path,
    reference_dir: Path | None,
    spec_ids: list[str],
    generation_repeats: int,
    target_valid_generations: int | None,
    fill_max_attempts: int | None,
    profile: str,
    prompt_profile_id: str,
    provider: str,
    model: str | None,
    base_url: str | None,
    timeout_seconds: float,
    max_completion_tokens: int | None,
    codex_reasoning_effort: str | None,
    created_by: str,
) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    base_url = base_url.rstrip("/") if base_url else None
    resolved_model = model or default_model_for_provider(provider)
    prompt_profile = direct_prompt_profile(prompt_profile_id)
    write_profile_manifest(
        out_dir,
        {
            "profile": profile,
            "prompt_profile": prompt_profile.id,
            "prompt_template_id": prompt_profile.template_id,
            "provider": provider,
            "model": resolved_model,
            "spec_dir": str(spec_dir),
            "reference_dir": str(reference_dir) if reference_dir else "",
            "generation_repeats": generation_repeats,
            "target_valid_generations": target_valid_generations or generation_repeats,
            "fill_max_attempts": fill_max_attempts,
            "created_by": created_by,
        },
    )
    rows: list[dict[str, Any]] = []
    refill_reports: list[dict[str, Any]] = []
    exhausted_specs: list[str] = []
    target_valid = target_valid_generations or generation_repeats
    max_attempts = fill_max_attempts or target_valid
    if max_attempts < target_valid:
        raise ValueError("--fill-max-attempts must be greater than or equal to the target valid generation count")
    for spec_path in selected_spec_paths(spec_dir, spec_ids):
        next_valid_index = 1

        async def run_attempt(attempt_index: int) -> dict[str, Any]:
            nonlocal next_valid_index
            generation_id = f"gen-{next_valid_index:03d}"
            attempt_id = f"attempt-{attempt_index:03d}"
            started_at = utc_now()
            monotonic_start = time.monotonic()
            status = "failed"
            returncode = 1
            error = ""
            try:
                row = await generate_direct_baseline_attempt(
                    spec_path=spec_path,
                    out_dir=out_dir,
                    generation_id=generation_id,
                    attempt_id=attempt_id,
                    provider=provider,
                    model=resolved_model,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    max_completion_tokens=max_completion_tokens,
                    codex_reasoning_effort=codex_reasoning_effort,
                    prompt_profile=prompt_profile,
                    reference_dir=reference_dir,
                )
                status = "completed"
                returncode = 0
                next_valid_index += 1
                return row
            except Exception as exc:
                error = safe_exception_detail(exc)
                raise
            finally:
                append_timing(
                    out_dir,
                    {
                        "phase": "generate",
                        "step": "direct_generate",
                        "key": f"{generation_id}-{spec_path.stem.zfill(3)}-{attempt_id}",
                        "generation_run_id": generation_id,
                        "attempt_id": attempt_id,
                        "status": status,
                        "error": error,
                        "started_at_utc": started_at,
                        "duration_seconds": round(time.monotonic() - monotonic_start, 3),
                        "command": created_by,
                        "returncode": returncode,
                    },
                )

        result = await collect_valid_attempts(
            target_valid=target_valid,
            max_attempts=max_attempts,
            run_attempt=run_attempt,
            metadata_for_attempt=lambda attempt_index: {
                "spec_id": spec_path.stem.zfill(3),
                "attempt_id": f"attempt-{attempt_index:03d}",
            },
        )
        rows.extend(result.values)
        if result.exhausted:
            exhausted_specs.append(spec_path.stem.zfill(3))
        refill_reports.append(
            {
                "spec_id": spec_path.stem.zfill(3),
                "target_valid": result.target_valid,
                "valid_count": len(result.values),
                "exhausted": result.exhausted,
                "attempts": [asdict(attempt) for attempt in result.attempts],
            }
        )
    write_checkpoint_manifest(out_dir, rows)
    write_json(out_dir / "refill_manifest.json", refill_reports)
    return 1 if exhausted_specs else 0


__all__ = [
    "generate_direct_baseline_attempt",
    "reference_path_for",
    "run_direct_baseline_generation",
    "selected_spec_paths",
]
