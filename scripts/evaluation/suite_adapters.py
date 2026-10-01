from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.artifacts import read_checkpoint_manifest_path
from core.config_safety import (
    redact_persisted_value,
    redact_sensitive_text,
    safe_exception_detail,
)
from core.model_call_logger import ModelCallLogger
from core.providers.codex import CODEX_BASE_URL, CodexAuthProvider
from core.providers.factory import build_text_model_client
from harnesses.catalog import get_harness_definition
from judge import DirectionalModelJudgeClient, evaluate_structured_model_pair_directional
from judge.directional import load_structured_model
from judge.evaluation_artifacts import (
    EvaluationArtifactError,
    artifact_map_from_payload,
    canonical_json_bytes,
    manifest_sha256,
    materialize_artifact,
    resolve_source_path,
    sha256_bytes,
    stable_file_bytes,
    storage_name,
    verify_materialized_artifact,
    write_json_atomic,
)
from judge.evaluation_contracts import (
    ArtifactDescriptor,
    CandidateRecord,
    CatalogGenerationSource,
    CommandAdapter,
    CommandGenerationSource,
    CommandJudgeSource,
    DirectionalJudgeSource,
    EvaluationSuite,
    GeneratorAdapterRequest,
    GeneratorAdapterResponse,
    JudgeAdapterRequest,
    JudgeAdapterResponse,
    JudgeResultRecord,
    MaterializedArtifact,
    SystemView,
    validate_portable_metadata,
)


ESSENTIAL_SUBPROCESS_ENVIRONMENT = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
)
APP_ROOT = Path(__file__).resolve().parents[2]


class EvaluationAdapterError(RuntimeError):
    pass


class EvaluationAdapterTimeout(EvaluationAdapterError):
    def __init__(self, *, attempts: int, duration_seconds: float) -> None:
        super().__init__("adapter timed out")
        self.attempts = attempts
        self.duration_seconds = duration_seconds


def safe_evaluation_error(error: BaseException, *, work_dir: Path) -> str:
    detail = safe_exception_detail(error)
    known_roots = {
        str(work_dir.absolute()),
        str(Path(__file__).resolve().parents[2]),
        str(Path.cwd().absolute()),
    }
    for root in sorted(known_roots, key=len, reverse=True):
        if root:
            detail = detail.replace(root, "$LOCAL_PATH")
            detail = detail.replace(root.replace("\\", "/"), "$LOCAL_PATH")
    detail = re.sub(
        r"(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/])[^\s\"'<>]+",
        "$LOCAL_PATH",
        detail,
    )
    detail = re.sub(
        r"(?<![:/A-Za-z0-9])/(?!/)[^\s\"'<>]+",
        "$LOCAL_PATH",
        detail,
    )
    return redact_sensitive_text(
        detail,
        redact_named_values=True,
        redact_url_fragments=True,
    )


def _prepared_case_index(prepared: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = (prepared.get("dataset") or {}).get("cases")
    if not isinstance(cases, list):
        raise EvaluationAdapterError("prepared dataset has no cases")
    return {
        str(case["case_id"]): case
        for case in cases
        if isinstance(case, dict) and case.get("case_id")
    }


def _source_views(suite: EvaluationSuite, source_id: str) -> list[SystemView]:
    return [view for view in suite.system_views if view.source_id == source_id]


def _sanitized_adapter_environment(adapter: CommandAdapter) -> dict[str, str]:
    allowed = set(ESSENTIAL_SUBPROCESS_ENVIRONMENT)
    allowed.update(adapter.environment_allowlist)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {name.upper() for name in allowed}
    }
    environment["PYTHONPATH"] = os.pathsep.join(
        str(path) for path in sys.path if path
    )
    return environment


def _adapter_executable(adapter: CommandAdapter) -> str:
    executable = adapter.argv[0]
    if executable.lower() in {"python", "python3", "py"}:
        stable_file_bytes(
            Path(sys.executable),
            label=f"adapter interpreter for {adapter.implementation_id!r}",
        )
        return sys.executable
    candidate = Path(executable)
    if candidate.is_absolute():
        stable_file_bytes(candidate, label=f"adapter {adapter.implementation_id!r}")
        return str(candidate)
    discovered = shutil.which(executable)
    if not discovered:
        raise EvaluationAdapterError(
            f"adapter executable is unavailable: {executable!r}"
        )
    stable_file_bytes(
        Path(discovered),
        label=f"adapter executable for {adapter.implementation_id!r}",
    )
    return discovered


def validate_command_adapter(adapter: CommandAdapter) -> dict[str, Any]:
    executable = _adapter_executable(adapter)
    executable_path = Path(executable)
    identity = {
        "implementation_id": adapter.implementation_id,
        "revision": adapter.revision,
        "executable": executable_path.name,
        "executable_sha256": sha256_bytes(
            stable_file_bytes(
                executable_path,
                label=f"adapter executable for {adapter.implementation_id!r}",
            )
        ),
        "environment_allowlist": list(adapter.environment_allowlist),
    }
    arguments = adapter.argv[1:]
    entrypoint: Path | None = None
    entrypoint_label: str | None = None
    if len(arguments) >= 2 and arguments[0] == "-m":
        module_name = arguments[1]
        module = importlib.util.find_spec(module_name)
        if module is None or not module.origin:
            raise EvaluationAdapterError(
                f"adapter module is unavailable: {module_name!r}"
            )
        entrypoint = Path(module.origin)
        entrypoint_label = module_name
    elif arguments and not arguments[0].startswith("-"):
        script = Path(arguments[0])
        if script.is_absolute():
            entrypoint = script
            entrypoint_label = script.name
    if entrypoint is not None:
        identity["entrypoint"] = entrypoint_label
        identity["entrypoint_sha256"] = sha256_bytes(
            stable_file_bytes(
                entrypoint,
                label=f"adapter entrypoint for {adapter.implementation_id!r}",
            )
        )
    return identity


def _run_adapter_process(
    *,
    adapter: CommandAdapter,
    request_path: Path,
    response_path: Path,
    work_dir: Path,
) -> tuple[int, float]:
    executable = _adapter_executable(adapter)
    command = [
        executable,
        *adapter.argv[1:],
        "--request",
        str(request_path),
        "--response",
        str(response_path),
    ]
    last_error = ""
    last_attempt_timed_out = False
    started = time.monotonic()
    for attempt in range(1, adapter.max_attempts + 1):
        try:
            response_path.unlink(missing_ok=True)
            completed = subprocess.run(
                command,
                cwd=work_dir,
                env=_sanitized_adapter_environment(adapter),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=adapter.timeout_seconds,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = "adapter timed out"
            last_attempt_timed_out = True
        except OSError as exc:
            last_error = safe_exception_detail(exc)
            last_attempt_timed_out = False
        else:
            if completed.returncode == 0 and response_path.is_file():
                return attempt, time.monotonic() - started
            last_error = (
                f"adapter exited with code {completed.returncode}"
                if completed.returncode
                else "adapter did not create its response"
            )
            last_attempt_timed_out = False
        if attempt < adapter.max_attempts:
            time.sleep(min(2.0, 0.2 * attempt))
    duration = time.monotonic() - started
    if last_attempt_timed_out:
        raise EvaluationAdapterTimeout(
            attempts=adapter.max_attempts,
            duration_seconds=duration,
        )
    raise EvaluationAdapterError(
        redact_sensitive_text(
            f"{adapter.implementation_id} failed: {last_error}",
            redact_named_values=True,
            redact_url_fragments=True,
        )
    )


def _load_adapter_response(path: Path, *, label: str) -> Any:
    payload = stable_file_bytes(path, label=label)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationAdapterError(f"{label} is not valid UTF-8 JSON") from exc


def _consume_adapter_response(
    path: Path,
    *,
    label: str,
    adapter: CommandAdapter,
    work_dir: Path,
) -> Any:
    try:
        payload = _load_adapter_response(path, label=label)
        validate_portable_metadata(payload, path=label)
        serialized = json.dumps(payload, ensure_ascii=False)
        for name in adapter.environment_allowlist:
            value = os.environ.get(name)
            if value and value in serialized:
                raise EvaluationAdapterError(
                    f"{label} reflected an allowlisted environment value"
                )
        forbidden_paths = [
            str(work_dir),
            *(
                argument
                for argument in adapter.argv
                if Path(argument).is_absolute()
            ),
        ]
        if any(value and value in serialized for value in forbidden_paths):
            raise EvaluationAdapterError(
                f"{label} reflected an absolute machine-local path"
            )
        return payload
    finally:
        path.unlink(missing_ok=True)


def _copy_adapter_candidate_artifacts(
    *,
    response: GeneratorAdapterResponse,
    source: CommandGenerationSource,
    views: list[SystemView],
    case_id: str,
    sample_id: str,
    work_dir: Path,
    attempts: int,
    duration_seconds: float,
) -> list[dict[str, Any]]:
    by_checkpoint = {view.checkpoint_or_view: view for view in views}
    unknown = sorted(set(response.artifacts_by_view) - set(by_checkpoint))
    if unknown:
        raise EvaluationAdapterError(
            "generator adapter returned undeclared views: " + ", ".join(unknown)
        )
    missing_views = sorted(set(by_checkpoint) - set(response.artifacts_by_view))
    if missing_views:
        raise EvaluationAdapterError(
            "generator adapter omitted declared views: "
            + ", ".join(missing_views)
        )
    output: list[dict[str, Any]] = []
    for checkpoint, artifacts in sorted(response.artifacts_by_view.items()):
        view = by_checkpoint[checkpoint]
        copied: dict[str, MaterializedArtifact] = {}
        missing_roles = sorted(
            source_role
            for source_role in view.artifact_roles.values()
            if source_role not in artifacts
        )
        if missing_roles:
            raise EvaluationAdapterError(
                f"generator view {view.system_id!r} omitted declared artifact "
                "roles: " + ", ".join(missing_roles)
            )
        for role, source_role in sorted(view.artifact_roles.items()):
            descriptor = artifacts[source_role]
            source_path = resolve_source_path(
                descriptor.path,
                manifest_dir=work_dir,
                allow_absolute=False,
            )
            destination = (
                work_dir
                / "artifacts"
                / "candidates"
                / storage_name(view.system_id)
                / storage_name(case_id)
                / storage_name(sample_id)
                / f"{storage_name(role)}{source_path.suffix}"
            )
            copied[role] = materialize_artifact(
                descriptor,
                manifest_dir=work_dir,
                destination=destination,
                work_dir=work_dir,
                label=(
                    f"command candidate {view.system_id!r}/{case_id!r}/"
                    f"{sample_id!r} artifact {role!r}"
                ),
                allow_absolute=False,
            )
        output.append(
            CandidateRecord(
                system_id=view.system_id,
                case_id=case_id,
                sample_id=sample_id,
                checkpoint_or_view=checkpoint,
                artifacts=copied,
                generator_provenance={
                    **response.provenance,
                    "source_kind": "command",
                    "source_id": source.source_id,
                    "implementation_id": source.adapter.implementation_id,
                    "revision": source.adapter.revision,
                },
                usage={
                    **(response.usage or {}),
                    "adapter_attempts": attempts,
                    "duration_seconds": round(duration_seconds, 6),
                },
            ).model_dump(mode="json")
        )
    return output


def _command_generation_job(
    *,
    source: CommandGenerationSource,
    views: list[SystemView],
    case: dict[str, Any],
    sample_index: int,
    work_dir: Path,
) -> list[dict[str, Any]]:
    case_id = str(case["case_id"])
    sample_id = f"sample-{sample_index:03d}"
    job_dir = (
        work_dir
        / "jobs"
        / "generation"
        / storage_name(source.source_id)
        / storage_name(case_id)
        / sample_id
    )
    request_path = job_dir / "request.json"
    response_path = job_dir / "response.json"
    result_path = job_dir / "result.json"
    request = GeneratorAdapterRequest(
        request_id=f"{source.source_id}:{case_id}:{sample_id}",
        source_id=source.source_id,
        system_views=views,
        case_id=case_id,
        sample_id=sample_id,
        inputs=artifact_map_from_payload(case["inputs"]),
        references=artifact_map_from_payload(case["references"]),
        output_dir=(job_dir / "output").relative_to(work_dir).as_posix(),
    )
    request_payload = request.model_dump(mode="json")
    request_hash = manifest_sha256(request_payload)
    if result_path.is_file():
        cached = _load_adapter_response(
            result_path,
            label="cached command generation result",
        )
        if not isinstance(cached, dict) or cached.get("request_sha256") != request_hash:
            raise EvaluationAdapterError(
                "command generation cache conflicts with the current request"
            )
        rows = cached.get("candidates")
        if not isinstance(rows, list):
            raise EvaluationAdapterError("cached command generation result is invalid")
        for row in rows:
            candidate = CandidateRecord.model_validate(row)
            for artifact in candidate.artifacts.values():
                verify_materialized_artifact(artifact, work_dir=work_dir)
        return rows
    write_json_atomic(request_path, request_payload)
    attempts, duration = _run_adapter_process(
        adapter=source.adapter,
        request_path=request_path,
        response_path=response_path,
        work_dir=work_dir,
    )
    response = GeneratorAdapterResponse.model_validate(
        _consume_adapter_response(
            response_path,
            label=f"generator response for {source.source_id!r}",
            adapter=source.adapter,
            work_dir=work_dir,
        )
    )
    if response.status != "completed":
        raise EvaluationAdapterError(
            f"generator adapter {source.adapter.implementation_id!r} reported failure"
        )
    candidates = _copy_adapter_candidate_artifacts(
        response=response,
        source=source,
        views=views,
        case_id=case_id,
        sample_id=sample_id,
        work_dir=work_dir,
        attempts=attempts,
        duration_seconds=duration,
    )
    write_json_atomic(
        result_path,
        {
            "request_sha256": request_hash,
            "attempts": attempts,
            "duration_seconds": round(duration, 6),
            "candidates": candidates,
        },
    )
    return candidates


def _materialized_path(
    descriptor: dict[str, Any],
    *,
    work_dir: Path,
) -> Path:
    return verify_materialized_artifact(descriptor, work_dir=work_dir)


def _prepare_catalog_input_tree(
    *,
    source: CatalogGenerationSource,
    prepared: dict[str, Any],
    work_dir: Path,
) -> tuple[Path, Path, dict[str, str]]:
    source_root = (
        work_dir / "catalog_inputs" / storage_name(source.source_id)
    )
    spec_dir = source_root / "specs"
    reference_dir = source_root / "references"
    spec_dir.mkdir(parents=True, exist_ok=True)
    reference_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    for case in _prepared_case_index(prepared).values():
        case_id = str(case["case_id"])
        storage_id = storage_name(case_id)
        mapping[storage_id] = case_id
        try:
            specification = case["inputs"][source.input_role]
            reference = case["references"][source.reference_role]
        except KeyError as exc:
            raise EvaluationAdapterError(
                f"catalog source {source.source_id!r} requires input role "
                f"{source.input_role!r} and reference role {source.reference_role!r}"
            ) from exc
        spec_source = _materialized_path(specification, work_dir=work_dir)
        reference_source = _materialized_path(reference, work_dir=work_dir)
        spec_target = spec_dir / f"{storage_id}.txt"
        reference_target = reference_dir / storage_id / "structured_model.json"
        spec_target.parent.mkdir(parents=True, exist_ok=True)
        reference_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(spec_source, spec_target)
        shutil.copyfile(reference_source, reference_target)
    write_json_atomic(source_root / "case_map.json", mapping)
    return spec_dir, reference_dir, mapping


def _run_catalog_command(
    command: list[str],
    *,
    work_dir: Path,
    timeout_seconds: float,
) -> None:
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[2],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(timeout_seconds, 60.0),
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise EvaluationAdapterError("catalog harness command timed out") from exc
    if completed.returncode != 0:
        detail = redact_sensitive_text(
            completed.stderr[-2000:] or completed.stdout[-2000:],
            redact_named_values=True,
            redact_url_fragments=True,
        )
        raise EvaluationAdapterError(
            f"catalog harness command failed with exit code "
            f"{completed.returncode}: {detail}"
        )


def _catalog_cli_path(path: Path) -> str:
    try:
        return os.path.relpath(Path(os.path.abspath(path)), APP_ROOT)
    except ValueError as exc:
        raise EvaluationAdapterError(
            "catalog evaluation work directories must be on the application "
            "filesystem volume so subprocess manifests remain portable"
        ) from exc


def _catalog_binding(source: CatalogGenerationSource) -> dict[str, Any]:
    binding = (source.model_bindings or {}).get("default")
    if not isinstance(binding, dict):
        binding = {}
    return {
        "provider": source.provider,
        "model": source.model,
        **binding,
    }


def _catalog_generation_manifest(
    *,
    source: CatalogGenerationSource,
    prepared: dict[str, Any],
    work_dir: Path,
    resume: bool,
) -> tuple[Path, dict[str, str]]:
    definition = get_harness_definition(source.harness_id)
    if definition is None:
        raise EvaluationAdapterError(
            f"catalog harness disappeared after preflight: {source.harness_id!r}"
        )
    spec_dir, reference_dir, mapping = _prepare_catalog_input_tree(
        source=source,
        prepared=prepared,
        work_dir=work_dir,
    )
    output_dir = (
        work_dir / "catalog_runs" / storage_name(source.source_id)
    )
    binding = _catalog_binding(source)
    if definition.family == "direct_baseline":
        command = [
            sys.executable,
            "-m",
            "scripts.generation.direct_baseline",
            "--spec-dir",
            _catalog_cli_path(spec_dir),
            "--reference-dir",
            _catalog_cli_path(reference_dir),
            "--out-dir",
            _catalog_cli_path(output_dir),
            "--generation-repeats",
            str(source.repetitions),
            "--target-valid-generations",
            str(source.target_valid_generations or source.repetitions),
            "--fill-max-attempts",
            str(
                source.fill_max_attempts
                or source.target_valid_generations
                or source.repetitions
            ),
            "--profile",
            source.source_id,
            "--prompt-profile",
            str(definition.prompt_profile or "schema_only_v1"),
            "--provider",
            source.provider,
            "--model",
            source.model,
            "--timeout-seconds",
            str(source.timeout_seconds),
            "--max-completion-tokens",
            str(binding.get("max_completion_tokens") or 32768),
        ]
        if source.provider == "codex" and source.codex_reasoning_effort:
            command.extend(
                ["--codex-reasoning-effort", source.codex_reasoning_effort]
            )
        if binding.get("base_url"):
            command.extend(["--base-url", str(binding["base_url"])])
        _run_catalog_command(
            command,
            work_dir=work_dir,
            timeout_seconds=source.timeout_seconds
            * max(source.repetitions, 1)
            * len(mapping),
        )
        return output_dir / "checkpoint_manifest.json", mapping
    if source.provider == "codex":
        raise EvaluationAdapterError(
            "structured-patch catalog harnesses do not support Codex generation"
        )
    command = [
        sys.executable,
        "-m",
        "scripts.generation.batch_harness",
        "--spec-dir",
        _catalog_cli_path(spec_dir),
        "--reference-dir",
        _catalog_cli_path(reference_dir),
        "--out-dir",
        _catalog_cli_path(output_dir),
        "--generation-repeats",
        str(source.repetitions),
        "--concurrency",
        "1",
        "--max-attempts",
        str(source.max_attempts),
        "--profile",
        source.source_id,
        "--provider",
        source.provider,
        "--model",
        source.model,
        "--timeout-seconds",
        str(source.timeout_seconds),
        "--max-completion-tokens",
        str(binding.get("max_completion_tokens") or 32768),
        "--harness-id",
        source.harness_id,
    ]
    if binding.get("base_url"):
        command.extend(["--base-url", str(binding["base_url"])])
    if resume:
        command.append("--resume")
    if source.runtime_config.get("auto_correction_sequence") is True:
        command.append("--auto-correction-sequence")
    elif source.runtime_config.get("auto_correction_sequence") is False:
        command.append("--no-auto-correction-sequence")
    correction_template_id = source.runtime_config.get(
        "correction_template_id"
    )
    if correction_template_id:
        command.extend(
            ["--correction-template-id", str(correction_template_id)]
        )
    _run_catalog_command(
        command,
        work_dir=work_dir,
        timeout_seconds=source.timeout_seconds
        * max(source.repetitions, 1)
        * len(mapping),
    )
    snapshot_dir = output_dir / "suite_snapshots"
    _run_catalog_command(
        [
            sys.executable,
            "-m",
            "scripts.evaluation.export_snapshots",
            "--run",
            _catalog_cli_path(output_dir),
            "--out-dir",
            _catalog_cli_path(snapshot_dir),
            "--spec-dir",
            _catalog_cli_path(spec_dir),
            "--reference-dir",
            _catalog_cli_path(reference_dir),
        ],
        work_dir=work_dir,
        timeout_seconds=max(source.timeout_seconds, 300.0),
    )
    selected_dir = output_dir / "suite_selected"
    _run_catalog_command(
        [
            sys.executable,
            "-m",
            "scripts.evaluation.select_protocol_checkpoints",
            "--snapshot-manifest",
            _catalog_cli_path(snapshot_dir / "snapshot_manifest.json"),
            "--output",
            _catalog_cli_path(selected_dir / "checkpoint_manifest.json"),
        ],
        work_dir=work_dir,
        timeout_seconds=max(source.timeout_seconds, 300.0),
    )
    return selected_dir / "checkpoint_manifest.json", mapping


def _copy_catalog_candidates(
    *,
    source: CatalogGenerationSource,
    views: list[SystemView],
    manifest_path: Path,
    case_mapping: dict[str, str],
    work_dir: Path,
) -> list[dict[str, Any]]:
    by_checkpoint = {view.checkpoint_or_view: view for view in views}
    candidates: list[dict[str, Any]] = []
    for row in read_checkpoint_manifest_path(manifest_path):
        checkpoint = str(row.get("checkpoint_label") or "")
        view = by_checkpoint.get(checkpoint)
        if view is None:
            continue
        storage_case = str(row.get("spec_id") or "")
        case_id = case_mapping.get(storage_case, storage_case)
        sample_id = str(row.get("generation_run_id") or "")
        source_model = Path(str(row["model_path"]))
        if not source_model.is_absolute():
            source_model = APP_ROOT / source_model
        usage = _catalog_candidate_usage(row, manifest_path=manifest_path)
        copied_model = materialize_artifact(
            ArtifactDescriptor(path=str(source_model)),
            manifest_dir=manifest_path.parent,
            destination=(
                work_dir
                / "artifacts"
                / "candidates"
                / storage_name(view.system_id)
                / storage_name(case_id)
                / storage_name(sample_id)
                / "model.json"
            ),
            work_dir=work_dir,
            label=(
                f"catalog candidate {view.system_id!r}/{case_id!r}/{sample_id!r}"
            ),
        )
        candidates.append(
            CandidateRecord(
                system_id=view.system_id,
                case_id=case_id,
                sample_id=sample_id,
                checkpoint_or_view=checkpoint,
                artifacts={"model": copied_model},
                generator_provenance={
                    "source_kind": "catalog_harness",
                    "source_id": source.source_id,
                    "harness_id": source.harness_id,
                    "definition_revision": source.definition_revision,
                    "provider": source.provider,
                    "model": source.model,
                },
                usage=usage,
            ).model_dump(mode="json")
        )
    expected = {
        (
            view.system_id,
            case_id,
            f"gen-{index:03d}",
            view.checkpoint_or_view,
        )
        for view in views
        for case_id in case_mapping.values()
        for index in range(1, source.repetitions + 1)
    }
    actual = {
        (
            row["system_id"],
            row["case_id"],
            row["sample_id"],
            row["checkpoint_or_view"],
        )
        for row in candidates
    }
    missing = expected - actual
    if missing:
        preview = ", ".join("/".join(item) for item in sorted(missing)[:5])
        raise EvaluationAdapterError(
            f"catalog source {source.source_id!r} did not produce all pinned "
            f"candidate views ({len(missing)} missing; first: {preview})"
        )
    return candidates


def _summarize_usage_steps(value: object) -> dict[str, Any] | None:
    if isinstance(value, dict):
        records = [value]
    elif isinstance(value, list):
        records = [row for row in value if isinstance(row, dict)]
    else:
        records = []
    if not records:
        return None
    totals: dict[str, int | float] = {}
    for record in records:
        for key, raw_value in record.items():
            if (
                isinstance(raw_value, (int, float))
                and not isinstance(raw_value, bool)
            ):
                totals[key] = totals.get(key, 0) + raw_value
    totals["calls"] = len(records)
    return redact_persisted_value(totals)


def _catalog_candidate_usage(
    row: dict[str, Any],
    *,
    manifest_path: Path,
) -> dict[str, Any] | None:
    source_row = row.get("source_row")
    source_payload = source_row if isinstance(source_row, dict) else row
    source_result = str(source_payload.get("source_result_path") or "")
    source_checkpoint = str(source_payload.get("source_checkpoint_path") or "")
    candidates: list[tuple[Path, str]] = []
    if source_result:
        candidates.append((Path(source_result), "usage_steps"))
    elif source_checkpoint:
        candidates.append(
            (Path(source_checkpoint).parent.parent / "result.json", "usage_steps")
        )
    model_path = Path(str(row.get("model_path") or ""))
    if model_path.name:
        candidates.append((model_path.parent / "raw_completion.json", "usage"))
    for path, field in candidates:
        if path.is_absolute():
            candidate = path
        else:
            app_relative = APP_ROOT / path
            manifest_relative = manifest_path.parent / path
            candidate = (
                app_relative if app_relative.is_file() else manifest_relative
            )
        if not candidate.is_file():
            continue
        payload = _load_adapter_response(
            candidate,
            label="catalog generation accounting",
        )
        if isinstance(payload, dict):
            summarized = _summarize_usage_steps(payload.get(field))
            if summarized is not None:
                return summarized
    return None


def _candidate_completeness_failures(
    *,
    suite: EvaluationSuite,
    case_ids: list[str],
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    identities = {
        (
            str(row["system_id"]),
            str(row["case_id"]),
            str(row["sample_id"]),
            str(row["checkpoint_or_view"]),
        )
        for row in candidates
    }
    failures: list[dict[str, Any]] = []
    for source in suite.generation_sources:
        views = _source_views(suite, source.source_id)
        if source.kind in {"catalog_harness", "command"}:
            sample_prefix = (
                "gen" if source.kind == "catalog_harness" else "sample"
            )
            expected = {
                (
                    view.system_id,
                    case_id,
                    f"{sample_prefix}-{index:03d}",
                    view.checkpoint_or_view,
                )
                for view in views
                for case_id in case_ids
                for index in range(1, source.repetitions + 1)
            }
            missing = expected - identities
        else:
            expected_pairs = {
                (
                    view.system_id,
                    case_id,
                    view.checkpoint_or_view,
                )
                for view in views
                for case_id in case_ids
            }
            actual_pairs = {
                (system_id, case_id, checkpoint)
                for system_id, case_id, _sample_id, checkpoint in identities
            }
            missing = {
                (system_id, case_id, "<any-sample>", checkpoint)
                for system_id, case_id, checkpoint in (
                    expected_pairs - actual_pairs
                )
            }
        if not missing:
            continue
        preview = [
            {
                "system_id": system_id,
                "case_id": case_id,
                "sample_id": sample_id,
                "checkpoint_or_view": checkpoint,
            }
            for system_id, case_id, sample_id, checkpoint in sorted(missing)[:20]
        ]
        failures.append(
            {
                "stage": "generation",
                "source_id": source.source_id,
                "kind": "missing_candidates",
                "missing_count": len(missing),
                "missing_preview": preview,
                "error": (
                    f"generation source omitted {len(missing)} declared "
                    "candidate output(s)"
                ),
            }
        )
    return failures


async def execute_generation_sources(
    *,
    suite: EvaluationSuite,
    prepared: dict[str, Any],
    work_dir: Path,
    resume: bool,
    keep_going: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = [
        row
        for rows in (prepared.get("imported_candidates") or {}).values()
        for row in rows
    ]
    failures: list[dict[str, Any]] = []
    cases = list(_prepared_case_index(prepared).values())
    for source in suite.generation_sources:
        views = _source_views(suite, source.source_id)
        if source.kind in {"candidate_manifest", "archived_models"}:
            continue
        try:
            if source.kind == "catalog_harness":
                manifest_path, mapping = await asyncio.to_thread(
                    _catalog_generation_manifest,
                    source=source,
                    prepared=prepared,
                    work_dir=work_dir,
                    resume=resume,
                )
                candidates.extend(
                    await asyncio.to_thread(
                        _copy_catalog_candidates,
                        source=source,
                        views=views,
                        manifest_path=manifest_path,
                        case_mapping=mapping,
                        work_dir=work_dir,
                    )
                )
                continue
            semaphore = asyncio.Semaphore(
                suite.execution.generation_concurrency
            )

            async def run_job(
                case: dict[str, Any],
                sample_index: int,
            ) -> list[dict[str, Any]]:
                async with semaphore:
                    return await asyncio.to_thread(
                        _command_generation_job,
                        source=source,
                        views=views,
                        case=case,
                        sample_index=sample_index,
                        work_dir=work_dir,
                    )

            jobs = [
                asyncio.create_task(run_job(case, sample_index))
                for case in cases
                for sample_index in range(1, source.repetitions + 1)
            ]
            for job in jobs:
                try:
                    candidates.extend(await job)
                except Exception as exc:
                    failures.append(
                        {
                            "stage": "generation",
                            "source_id": source.source_id,
                            "error": safe_evaluation_error(
                                exc,
                                work_dir=work_dir,
                            ),
                        }
                    )
                    if not keep_going:
                        for pending in jobs:
                            pending.cancel()
                        await asyncio.gather(*jobs, return_exceptions=True)
                        raise
        except Exception as exc:
            if not failures or failures[-1].get("source_id") != source.source_id:
                failures.append(
                    {
                        "stage": "generation",
                        "source_id": source.source_id,
                        "error": safe_evaluation_error(
                            exc,
                            work_dir=work_dir,
                        ),
                    }
                )
            if not keep_going:
                raise
    unique = {
        (
            row["system_id"],
            row["case_id"],
            row["sample_id"],
            row["checkpoint_or_view"],
        )
        for row in candidates
    }
    if len(unique) != len(candidates):
        raise EvaluationAdapterError("candidate identities collide across sources")
    completeness_failures = _candidate_completeness_failures(
        suite=suite,
        case_ids=[str(case["case_id"]) for case in cases],
        candidates=candidates,
    )
    failures.extend(completeness_failures)
    if completeness_failures and not keep_going:
        raise EvaluationAdapterError(
            "generation did not produce every declared candidate output"
        )
    return sorted(
        candidates,
        key=lambda row: (
            row["system_id"],
            row["case_id"],
            row["sample_id"],
            row["checkpoint_or_view"],
        ),
    ), failures


def _command_judge_job(
    *,
    judge: CommandJudgeSource,
    suite: EvaluationSuite,
    candidate: CandidateRecord,
    case: dict[str, Any],
    repeat_index: int,
    work_dir: Path,
) -> JudgeResultRecord:
    job_dir = (
        work_dir
        / "jobs"
        / "judging"
        / storage_name(judge.judge_id)
        / storage_name(candidate.system_id)
        / storage_name(candidate.case_id)
        / storage_name(candidate.sample_id)
        / f"repeat-{repeat_index:03d}"
    )
    request_path = job_dir / "request.json"
    response_path = job_dir / "response.json"
    result_path = job_dir / "result.json"
    request = JudgeAdapterRequest(
        request_id=(
            f"{judge.judge_id}:{candidate.system_id}:{candidate.case_id}:"
            f"{candidate.sample_id}:{repeat_index}"
        ),
        judge_id=judge.judge_id,
        repeat_index=repeat_index,
        candidate=candidate,
        inputs=artifact_map_from_payload(case["inputs"]),
        references=artifact_map_from_payload(case["references"]),
        declared_metrics=suite.metrics,
    )
    request_payload = request.model_dump(mode="json")
    request_hash = manifest_sha256(request_payload)
    if result_path.is_file():
        cached = _load_adapter_response(
            result_path,
            label="cached command judge result",
        )
        if not isinstance(cached, dict) or cached.get("request_sha256") != request_hash:
            raise EvaluationAdapterError(
                "command judge cache conflicts with the current request"
            )
        return JudgeResultRecord.model_validate(cached["result"])
    write_json_atomic(request_path, request_payload)
    try:
        attempts, duration = _run_adapter_process(
            adapter=judge.adapter,
            request_path=request_path,
            response_path=response_path,
            work_dir=work_dir,
        )
        response = JudgeAdapterResponse.model_validate(
            _consume_adapter_response(
                response_path,
                label=f"judge response for {judge.judge_id!r}",
                adapter=judge.adapter,
                work_dir=work_dir,
            )
        )
        if response.status == "completed":
            expected_metrics = {
                metric.metric_id
                for metric in suite.metrics
                if metric.repeat_reduction in {"mean", "median"}
            }
            actual_metrics = set(response.metrics)
            missing_metrics = sorted(expected_metrics - actual_metrics)
            unexpected_metrics = sorted(actual_metrics - expected_metrics)
            if missing_metrics or unexpected_metrics:
                details: list[str] = []
                if missing_metrics:
                    details.append("missing " + ", ".join(missing_metrics))
                if unexpected_metrics:
                    details.append(
                        "unexpected " + ", ".join(unexpected_metrics)
                    )
                raise EvaluationAdapterError(
                    f"judge {judge.judge_id!r} metric contract mismatch: "
                    + "; ".join(details)
                )
        result = JudgeResultRecord(
            result_id=request.request_id,
            judge_id=judge.judge_id,
            system_id=candidate.system_id,
            case_id=candidate.case_id,
            sample_id=candidate.sample_id,
            checkpoint_or_view=candidate.checkpoint_or_view,
            repeat_index=repeat_index,
            status="completed" if response.status == "completed" else "failed",
            metrics=response.metrics,
            notes=(
                redact_sensitive_text(
                    response.notes,
                    redact_named_values=True,
                    redact_url_fragments=True,
                )
                if response.notes
                else None
            ),
            details=redact_persisted_value(response.details),
            usage=redact_persisted_value(
                {
                    **(response.usage or {}),
                    "adapter_attempts": attempts,
                    "duration_seconds": round(duration, 6),
                }
            ),
            error=(
                redact_sensitive_text(
                    response.error,
                    redact_named_values=True,
                    redact_url_fragments=True,
                )
                if response.error
                else None
            ),
        )
    except EvaluationAdapterTimeout as exc:
        attempts = exc.attempts
        duration = exc.duration_seconds
        result = JudgeResultRecord(
            result_id=request.request_id,
            judge_id=judge.judge_id,
            system_id=candidate.system_id,
            case_id=candidate.case_id,
            sample_id=candidate.sample_id,
            checkpoint_or_view=candidate.checkpoint_or_view,
            repeat_index=repeat_index,
            status="timeout",
            error="judge adapter timed out",
        )
    write_json_atomic(
        result_path,
        {
            "request_sha256": request_hash,
            "attempts": attempts,
            "duration_seconds": round(duration, 6),
            "result": result.model_dump(mode="json"),
        },
    )
    return result


async def _directional_judge_job(
    *,
    judge: DirectionalJudgeSource,
    candidate: CandidateRecord,
    case: dict[str, Any],
    repeat_index: int,
    work_dir: Path,
) -> JudgeResultRecord:
    result_id = (
        f"{judge.judge_id}:{candidate.system_id}:{candidate.case_id}:"
        f"{candidate.sample_id}:{repeat_index}"
    )
    job_dir = (
        work_dir
        / "jobs"
        / "judging"
        / storage_name(judge.judge_id)
        / storage_name(candidate.system_id)
        / storage_name(candidate.case_id)
        / storage_name(candidate.sample_id)
        / f"repeat-{repeat_index:03d}"
    )
    result_path = job_dir / "result.json"
    request_identity = {
        "result_id": result_id,
        "judge": judge.model_dump(mode="json"),
        "candidate": candidate.model_dump(mode="json"),
        "case_inputs": case["inputs"],
        "case_references": case["references"],
    }
    request_hash = manifest_sha256(request_identity)
    if result_path.is_file():
        cached = _load_adapter_response(
            result_path,
            label="cached directional judge result",
        )
        if not isinstance(cached, dict) or cached.get("request_sha256") != request_hash:
            raise EvaluationAdapterError(
                "directional judge cache conflicts with the current request"
            )
        return JudgeResultRecord.model_validate(cached["result"])
    try:
        candidate_artifact = candidate.artifacts[judge.candidate_role]
        specification_artifact = case["inputs"][judge.input_role]
        reference_artifact = case["references"][judge.reference_role]
    except KeyError as exc:
        raise EvaluationAdapterError(
            f"directional judge {judge.judge_id!r} requires candidate role "
            f"{judge.candidate_role!r}, input role {judge.input_role!r}, and "
            f"reference role {judge.reference_role!r}"
        ) from exc
    predicted_path = verify_materialized_artifact(
        candidate_artifact,
        work_dir=work_dir,
    )
    spec_path = _materialized_path(specification_artifact, work_dir=work_dir)
    gold_path = _materialized_path(reference_artifact, work_dir=work_dir)
    client = build_text_model_client(
        provider=judge.provider,
        model=judge.model,
        timeout_seconds=judge.timeout_seconds,
        reasoning_effort=judge.reasoning_effort,
        response_format_json_object=True,
    )
    logger = ModelCallLogger(
        job_id=storage_name(result_id),
        log_dir=job_dir / "model_calls",
    )
    started = time.monotonic()
    score: dict[str, Any] | None = None
    attempts = 0
    for attempts in range(1, judge.max_attempts + 1):
        try:
            score = await evaluate_structured_model_pair_directional(
                gold_model=load_structured_model(gold_path),
                predicted_model=load_structured_model(predicted_path),
                specification=spec_path.read_text(encoding="utf-8"),
                judge_client=DirectionalModelJudgeClient(
                    client,
                    logger=logger,
                    prompt_profile_id=judge.prompt_profile,
                ),
                output_dir=job_dir,
            )
            break
        except Exception:
            if attempts >= judge.max_attempts:
                raise
            await asyncio.sleep(min(2.0, 0.2 * attempts))
    if score is None:
        raise EvaluationAdapterError("directional judge produced no score")
    aggregate = score["directional_semantic_score"]["aggregate"]
    result = JudgeResultRecord(
        result_id=result_id,
        judge_id=judge.judge_id,
        system_id=candidate.system_id,
        case_id=candidate.case_id,
        sample_id=candidate.sample_id,
        checkpoint_or_view=candidate.checkpoint_or_view,
        repeat_index=repeat_index,
        status="completed",
        metrics={
            metric_id: float(aggregate[metric_id])
            for metric_id in ("precision", "recall", "f1", "macro_f1")
        },
        details={
            "directional_semantic_score": score["directional_semantic_score"],
            "judge_prompt_profile": judge.prompt_profile,
        },
        usage={
            **(
                score.get("judge_usage")
                if isinstance(score.get("judge_usage"), dict)
                else {}
            ),
            "calls": (
                int(score["judge_usage"].get("calls") or attempts)
                if isinstance(score.get("judge_usage"), dict)
                else attempts
            ),
            "attempts": attempts,
            "duration_seconds": round(time.monotonic() - started, 6),
        },
    )
    write_json_atomic(
        result_path,
        {
            "request_sha256": request_hash,
            "attempts": attempts,
            "duration_seconds": round(time.monotonic() - started, 6),
            "result": result.model_dump(mode="json"),
        },
    )
    return result


async def execute_judges(
    *,
    suite: EvaluationSuite,
    prepared: dict[str, Any],
    candidates: list[dict[str, Any]],
    work_dir: Path,
    keep_going: bool,
) -> tuple[list[JudgeResultRecord], list[dict[str, Any]]]:
    results = [
        JudgeResultRecord.model_validate(row)
        for rows in (prepared.get("imported_results") or {}).values()
        for row in rows
    ]
    failures: list[dict[str, Any]] = [
        {
            "stage": "judging",
            "judge_id": result.judge_id,
            "system_id": result.system_id,
            "case_id": result.case_id,
            "sample_id": result.sample_id,
            "repeat_index": result.repeat_index,
            "status": result.status,
            "error": redact_sensitive_text(
                result.error or "stored judge result reported failure",
                redact_named_values=True,
                redact_url_fragments=True,
            ),
        }
        for result in results
        if result.status != "completed"
    ]
    if failures and not keep_going:
        raise EvaluationAdapterError(
            "stored judge-result manifest contains failed evaluations; "
            "use --keep-going to report partial results"
        )
    case_index = _prepared_case_index(prepared)
    semaphore = asyncio.Semaphore(suite.execution.judge_concurrency)

    async def run_job(
        judge: Any,
        candidate_payload: dict[str, Any],
        repeat_index: int,
    ) -> JudgeResultRecord:
        candidate = CandidateRecord.model_validate(candidate_payload)
        case = case_index.get(candidate.case_id)
        if case is None:
            raise EvaluationAdapterError(
                f"candidate references unknown case {candidate.case_id!r}"
            )
        async with semaphore:
            if judge.kind == "command":
                return await asyncio.to_thread(
                    _command_judge_job,
                    judge=judge,
                    suite=suite,
                    candidate=candidate,
                    case=case,
                    repeat_index=repeat_index,
                    work_dir=work_dir,
                )
            return await _directional_judge_job(
                judge=judge,
                candidate=candidate,
                case=case,
                repeat_index=repeat_index,
                work_dir=work_dir,
            )

    jobs: list[tuple[Any, dict[str, Any], int, asyncio.Task[JudgeResultRecord]]] = []
    for judge in suite.judges:
        if judge.kind == "stored_result_manifest":
            continue
        for candidate in candidates:
            for repeat_index in range(1, judge.repetitions + 1):
                jobs.append(
                    (
                        judge,
                        candidate,
                        repeat_index,
                        asyncio.create_task(
                            run_job(judge, candidate, repeat_index)
                        ),
                    )
                )
    for judge, candidate, repeat_index, job in jobs:
        try:
            result = await job
        except Exception as exc:
            failure = {
                "stage": "judging",
                "judge_id": judge.judge_id,
                "system_id": candidate["system_id"],
                "case_id": candidate["case_id"],
                "sample_id": candidate["sample_id"],
                "repeat_index": repeat_index,
                "error": safe_evaluation_error(
                            exc,
                            work_dir=work_dir,
                ),
            }
            failures.append(failure)
            results.append(
                JudgeResultRecord(
                    result_id=(
                        f"{judge.judge_id}:{candidate['system_id']}:"
                        f"{candidate['case_id']}:{candidate['sample_id']}:"
                        f"{repeat_index}"
                    ),
                    judge_id=judge.judge_id,
                    system_id=candidate["system_id"],
                    case_id=candidate["case_id"],
                    sample_id=candidate["sample_id"],
                    checkpoint_or_view=candidate["checkpoint_or_view"],
                    repeat_index=repeat_index,
                    status="failed",
                    error=safe_evaluation_error(
                        exc,
                        work_dir=work_dir,
                    ),
                )
            )
            if not keep_going:
                for _judge, _candidate, _repeat, pending in jobs:
                    pending.cancel()
                await asyncio.gather(
                    *(pending for *_rest, pending in jobs),
                    return_exceptions=True,
                )
                raise
        else:
            results.append(result)
            if result.status == "completed":
                continue
            failure = {
                "stage": "judging",
                "judge_id": result.judge_id,
                "system_id": result.system_id,
                "case_id": result.case_id,
                "sample_id": result.sample_id,
                "repeat_index": result.repeat_index,
                "status": result.status,
                "error": redact_sensitive_text(
                    result.error or "judge adapter reported failure",
                    redact_named_values=True,
                    redact_url_fragments=True,
                ),
            }
            failures.append(failure)
            if not keep_going:
                for _judge, _candidate, _repeat, pending in jobs:
                    pending.cancel()
                await asyncio.gather(
                    *(pending for *_rest, pending in jobs),
                    return_exceptions=True,
                )
                raise EvaluationAdapterError(
                    f"judge {result.judge_id!r} reported {result.status}"
                )
    return sorted(results, key=lambda row: row.result_id), failures


def _gemini_model_ids(api_key: str) -> set[str]:
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/openai/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "conceptual-model-generator-evaluation/1",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload.get("data") if isinstance(payload, dict) else None
    return {
        str(row.get("id") or "").removeprefix("models/")
        for row in rows or []
        if isinstance(row, dict) and row.get("id")
    }


def _codex_model_ids() -> set[str] | None:
    credentials = CodexAuthProvider().get()
    headers = {
        "Authorization": f"Bearer {credentials.access_token}",
        "User-Agent": "conceptual-model-generator-evaluation/1",
    }
    if credentials.account_id:
        headers["ChatGPT-Account-ID"] = credentials.account_id
    request = urllib.request.Request(
        f"{CODEX_BASE_URL}/models",
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in {404, 405}:
            return None
        raise
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    return {
        str(row.get("id") or "")
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


def verify_provider_model(provider: str, model: str) -> dict[str, Any]:
    if provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not key:
            raise EvaluationAdapterError(
                "GEMINI_API_KEY is required by the evaluation suite"
            )
        available = _gemini_model_ids(key)
        if model not in available:
            raise EvaluationAdapterError(
                f"pinned Gemini model {model!r} is not available"
            )
        return {"provider": provider, "model": model, "availability": "verified"}
    if provider == "codex":
        available = _codex_model_ids()
        if available is None:
            raise EvaluationAdapterError(
                "the Codex provider did not expose model availability metadata; "
                f"cannot verify pinned model {model!r} before paid work"
            )
        if model not in available:
            raise EvaluationAdapterError(
                f"pinned Codex model {model!r} is not available"
            )
        return {
            "provider": provider,
            "model": model,
            "availability": "verified",
        }
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        raise EvaluationAdapterError(
            "NVIDIA_API_KEY is required by the evaluation suite"
        )
    return {
        "provider": provider,
        "model": model,
        "availability": "credential_verified",
    }


def preflight_suite(
    *,
    suite: EvaluationSuite,
    prepared: dict[str, Any],
) -> dict[str, Any]:
    case_index = _prepared_case_index(prepared)
    adapter_identities: list[dict[str, Any]] = []
    provider_pairs: set[tuple[str, str]] = set()
    for source in suite.generation_sources:
        if source.kind == "command":
            adapter_identities.append(validate_command_adapter(source.adapter))
        elif source.kind == "catalog_harness":
            provider_pairs.add((source.provider, source.model))
            for case in case_index.values():
                if source.input_role not in case["inputs"]:
                    raise EvaluationAdapterError(
                        f"case {case['case_id']!r} lacks catalog input role "
                        f"{source.input_role!r}"
                    )
                if source.reference_role not in case["references"]:
                    raise EvaluationAdapterError(
                        f"case {case['case_id']!r} lacks catalog reference role "
                        f"{source.reference_role!r}"
                    )
    for judge in suite.judges:
        if judge.kind == "command":
            adapter_identities.append(validate_command_adapter(judge.adapter))
        elif judge.kind == "directional_structured_model_v1":
            provider_pairs.add((judge.provider, judge.model))
            for case in case_index.values():
                if judge.input_role not in case["inputs"]:
                    raise EvaluationAdapterError(
                        f"case {case['case_id']!r} lacks directional-judge "
                        f"input role {judge.input_role!r}"
                    )
                if judge.reference_role not in case["references"]:
                    raise EvaluationAdapterError(
                        f"case {case['case_id']!r} lacks directional-judge "
                        f"reference role {judge.reference_role!r}"
                    )
            missing_views = [
                view.system_id
                for view in suite.system_views
                if judge.candidate_role not in view.artifact_roles
            ]
            if missing_views:
                raise EvaluationAdapterError(
                    f"directional judge candidate role {judge.candidate_role!r} "
                    "is absent from system views: " + ", ".join(missing_views)
                )
    provider_status: list[dict[str, Any]] = []
    for provider, model in sorted(provider_pairs):
        try:
            provider_status.append(verify_provider_model(provider, model))
        except EvaluationAdapterError:
            raise
        except Exception as exc:
            raise EvaluationAdapterError(
                f"could not verify pinned {provider} model {model!r}: "
                f"{safe_exception_detail(exc)}"
            ) from exc
    return {
        "status": "completed",
        "adapter_identities": adapter_identities,
        "provider_models": provider_status,
        "plan": prepared["plan"],
    }


def build_fake_provider_argument_parser() -> argparse.ArgumentParser:
    """Public only so fake-provider end-to-end tests can share the CLI shape."""

    return argparse.ArgumentParser(add_help=False)


__all__ = [
    "EvaluationAdapterError",
    "execute_generation_sources",
    "execute_judges",
    "preflight_suite",
    "safe_evaluation_error",
    "validate_command_adapter",
    "verify_provider_model",
]
