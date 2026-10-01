from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from core.build_provenance import current_build_identity
from core.config_safety import redact_persisted_value
from harnesses.catalog import get_harness_definition, materialize_harness_run_spec
from judge import DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS
from judge.evaluation_artifacts import (
    EvaluationArtifactError,
    canonical_json_bytes,
    manifest_sha256,
    materialize_artifact,
    prepare_dataset,
    resolve_source_path,
    sha256_bytes,
    stable_file_bytes,
    storage_name,
    verify_materialized_artifact,
    write_json_atomic,
    write_bytes_atomic,
)
from judge.evaluation_contracts import (
    ArchivedModelGenerationSource,
    ArtifactDescriptor,
    CandidateManifestGenerationSource,
    CandidateRecord,
    EvaluationCandidateManifest,
    EvaluationClaimsManifest,
    EvaluationDataset,
    EvaluationSuite,
    JudgeResultRecord,
    MaterializedArtifact,
    StoredJudgeResultManifest,
    StoredResultJudgeSource,
)


PREPARED_SUITE_FILENAME = "prepared_suite.json"
RUN_STATE_FILENAME = "evaluation_run.json"
PREPARATION_MARKER_FILENAME = ".evaluation-preparing.json"


class EvaluationWorkspaceError(RuntimeError):
    pass


def _load_json_file(path: Path, *, label: str) -> Any:
    payload = stable_file_bytes(path, label=label)
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationWorkspaceError(f"{label} is not valid UTF-8 JSON") from exc


def load_suite(path: Path) -> EvaluationSuite:
    return EvaluationSuite.model_validate(
        _load_json_file(path, label="evaluation suite manifest")
    )


def load_claims(path: Path) -> EvaluationClaimsManifest:
    return EvaluationClaimsManifest.model_validate(
        _load_json_file(path, label="evaluation claims manifest")
    )


def suite_declaration_sha256(suite: EvaluationSuite) -> str:
    return manifest_sha256(suite.model_dump(mode="json"))


def _preparation_marker(suite: EvaluationSuite) -> dict[str, Any]:
    build_identity = current_build_identity().detached_dict()
    return {
        "artifact_kind": "evaluation_preparation",
        "schema_version": 1,
        "suite_id": suite.suite_id,
        "suite_declaration_sha256": suite_declaration_sha256(suite),
        "build_canonical_sha256": build_identity["canonical_sha256"],
    }


def _validate_preparation_marker(
    *,
    suite: EvaluationSuite,
    marker_path: Path,
) -> None:
    marker = _load_json_file(
        marker_path,
        label="evaluation preparation marker",
    )
    if marker != _preparation_marker(suite):
        raise EvaluationWorkspaceError(
            "partial evaluation preparation does not match this suite and build"
        )


def _initial_run_state(
    *,
    suite: EvaluationSuite,
    prepared: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    return {
        "artifact_kind": "evaluation_run",
        "schema_version": 1,
        "suite_id": suite.suite_id,
        "suite_declaration_sha256": suite_declaration_sha256(suite),
        "prepared_sha256": prepared["prepared_sha256"],
        "mode": mode,
        "status": "prepared",
        "stages": {},
        "plan": prepared["plan"],
    }


def _safe_source_summary(source: Any) -> dict[str, Any]:
    payload = source.model_dump(mode="json")
    for field in ("manifest", "archive_root"):
        value = payload.get(field)
        if value:
            raw_path = (
                str(value.get("path") or "")
                if isinstance(value, dict)
                else str(value)
            )
            payload[field] = {
                "source_name": Path(raw_path).name,
                "declaration_sha256": manifest_sha256(raw_path),
            }
    adapter = payload.get("adapter")
    if isinstance(adapter, dict):
        argv = adapter.get("argv")
        if isinstance(argv, list):
            adapter["argv"] = [
                f"$ABS/{Path(argument).name}"
                if Path(argument).is_absolute()
                else argument
                for argument in argv
            ]
        adapter["environment_allowlist"] = list(
            adapter.get("environment_allowlist") or []
        )
    return redact_persisted_value(payload)


def _safe_suite_summary(suite: EvaluationSuite) -> dict[str, Any]:
    return {
        "artifact_kind": suite.artifact_kind,
        "schema_version": suite.schema_version,
        "suite_id": suite.suite_id,
        "generation_sources": [
            _safe_source_summary(source) for source in suite.generation_sources
        ],
        "system_views": [
            view.model_dump(mode="json") for view in suite.system_views
        ],
        "judges": [_safe_source_summary(judge) for judge in suite.judges],
        "metrics": [metric.model_dump(mode="json") for metric in suite.metrics],
        "comparisons": [
            comparison.model_dump(mode="json")
            for comparison in suite.comparisons
        ],
        "statistics": suite.statistics.model_dump(mode="json"),
        "execution": suite.execution.model_dump(mode="json"),
        "metadata": redact_persisted_value(suite.metadata),
    }


def _validate_catalog_sources(suite: EvaluationSuite) -> None:
    for source in suite.generation_sources:
        if source.kind != "catalog_harness":
            continue
        definition = get_harness_definition(source.harness_id)
        if definition is None or not definition.runnable:
            raise EvaluationWorkspaceError(
                f"catalog harness {source.harness_id!r} is not runnable"
            )
        if definition.definition_revision != source.definition_revision:
            raise EvaluationWorkspaceError(
                f"catalog harness {source.harness_id!r} revision mismatch: "
                f"expected {source.definition_revision!r}, found "
                f"{definition.definition_revision!r}"
            )
        views = [
            view
            for view in suite.system_views
            if view.source_id == source.source_id
        ]
        if any(
            view.artifact_roles != {"model": "model"}
            for view in views
        ):
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} exposes only the "
                "structured model artifact"
            )
        supported_checkpoints = (
            {"single_shot_schema"}
            if definition.family == "direct_baseline"
            else {
                "first_valid_draft",
                "pre_posthoc",
                "final_guarded_posthoc",
            }
        )
        unsupported_checkpoints = sorted(
            {
                view.checkpoint_or_view
                for view in views
                if view.checkpoint_or_view not in supported_checkpoints
            }
        )
        if unsupported_checkpoints:
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} declares unsupported "
                "checkpoint views: " + ", ".join(unsupported_checkpoints)
            )
        allowed_runtime_keys = (
            {"prompt_profile", "auto_correction_sequence"}
            if definition.family == "direct_baseline"
            else {
                "auto_correction_sequence",
                "correction_template_id",
            }
        )
        unsupported_runtime_keys = sorted(
            set(source.runtime_config) - allowed_runtime_keys
        )
        if unsupported_runtime_keys:
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} contains workflow "
                "overrides unsupported by its script executor: "
                + ", ".join(unsupported_runtime_keys)
            )
        if definition.family == "direct_baseline":
            if source.runtime_config.get(
                "prompt_profile",
                definition.prompt_profile,
            ) != definition.prompt_profile:
                raise EvaluationWorkspaceError(
                    f"catalog source {source.source_id!r} prompt profile does "
                    "not match its pinned harness definition"
                )
            if source.runtime_config.get("auto_correction_sequence") not in {
                None,
                False,
            }:
                raise EvaluationWorkspaceError(
                    f"catalog source {source.source_id!r} cannot enable a "
                    "correction sequence"
                )
        elif (
            source.target_valid_generations is not None
            or source.fill_max_attempts is not None
        ):
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} uses direct-generation "
                "fill controls with a structured-patch harness"
            )
        if set(source.model_bindings) - {"default"}:
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} declares model-binding "
                "slots unsupported by its script executor"
            )
        raw_binding = source.model_bindings.get("default") or {}
        if not isinstance(raw_binding, dict):
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} default model binding "
                "must be an object"
            )
        allowed_binding_keys = {
            "provider",
            "model",
            "base_url",
            "timeout_seconds",
            "max_completion_tokens",
            "reasoning_effort",
        }
        unsupported_binding_keys = sorted(
            set(raw_binding) - allowed_binding_keys
        )
        if unsupported_binding_keys:
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} contains model-binding "
                "fields unsupported by its script executor: "
                + ", ".join(unsupported_binding_keys)
            )
        if (
            raw_binding.get("timeout_seconds") is not None
            and float(raw_binding["timeout_seconds"])
            != float(source.timeout_seconds)
        ):
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} timeout conflicts with "
                "its default model binding"
            )
        binding_reasoning = raw_binding.get("reasoning_effort")
        if (
            definition.family != "direct_baseline"
            and binding_reasoning
        ) or (
            source.provider != "codex"
            and binding_reasoning
        ):
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} reasoning effort is not "
                "supported by its script executor"
            )
        if (
            source.provider == "codex"
            and binding_reasoning != source.codex_reasoning_effort
        ):
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} Codex reasoning effort "
                "conflicts with its default model binding"
            )
        if source.provider != "codex" and source.codex_reasoning_effort:
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} declares Codex reasoning "
                "for a non-Codex provider"
            )
        bindings = source.model_bindings or {
            "default": {
                "provider": source.provider,
                "model": source.model,
            }
        }
        materialized = materialize_harness_run_spec(
            source.harness_id,
            expected_definition_revision=source.definition_revision,
            runtime_config_override=source.runtime_config,
            model_bindings=bindings,
        )
        if (
            any(
                view.checkpoint_or_view == "final_guarded_posthoc"
                for view in views
            )
            and not materialized.effective_config.auto_correction_sequence
        ):
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} cannot expose "
                "final_guarded_posthoc while automatic correction is disabled"
            )
        if str(materialized.model_bindings["default"].provider) != source.provider:
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} provider does not match "
                "its default model binding"
            )
        if str(materialized.model_bindings["default"].model) != source.model:
            raise EvaluationWorkspaceError(
                f"catalog source {source.source_id!r} model does not match "
                "its default model binding"
            )


def _validate_directional_judges(suite: EvaluationSuite) -> None:
    known = set(DIRECTIONAL_JUDGE_PROMPT_PROFILE_IDS)
    for judge in suite.judges:
        if (
            judge.kind == "directional_structured_model_v1"
            and judge.prompt_profile not in known
        ):
            raise EvaluationWorkspaceError(
                f"directional judge {judge.judge_id!r} uses unknown prompt "
                f"profile {judge.prompt_profile!r}"
            )
    directional_metrics = {
        "precision",
        "recall",
        "f1",
        "macro_f1",
    }
    declared = {metric.metric_id for metric in suite.metrics}
    if any(
        judge.kind == "directional_structured_model_v1"
        for judge in suite.judges
    ) and not directional_metrics.issubset(declared):
        missing = ", ".join(sorted(directional_metrics - declared))
        raise EvaluationWorkspaceError(
            "directional judge suites must declare metrics: " + missing
        )


def _dataset_path(suite: EvaluationSuite, suite_path: Path) -> Path:
    return resolve_source_path(
        suite.dataset,
        manifest_dir=suite_path.parent,
    )


def _claims_path(suite: EvaluationSuite, suite_path: Path) -> Path | None:
    if not suite.claims:
        return None
    return resolve_source_path(
        suite.claims,
        manifest_dir=suite_path.parent,
    )


def _copy_candidate_artifact(
    *,
    descriptor: MaterializedArtifact,
    manifest_dir: Path,
    destination: Path,
    work_dir: Path,
    label: str,
) -> MaterializedArtifact:
    source_descriptor = ArtifactDescriptor(
        path=descriptor.path,
        media_type=descriptor.media_type,
        schema_id=descriptor.schema_id,
        sha256=descriptor.sha256,
        size_bytes=descriptor.size_bytes,
    )
    return materialize_artifact(
        source_descriptor,
        manifest_dir=manifest_dir,
        destination=destination,
        work_dir=work_dir,
        label=label,
    )


def _materialize_source_manifest(
    descriptor: ArtifactDescriptor,
    *,
    manifest_dir: Path,
    destination: Path,
    work_dir: Path,
    label: str,
    schema_id: str,
) -> dict[str, Any]:
    copied = materialize_artifact(
        descriptor,
        manifest_dir=manifest_dir,
        destination=destination,
        work_dir=work_dir,
        label=label,
    )
    return copied.model_copy(
        update={
            "media_type": "application/json",
            "schema_id": schema_id,
        }
    ).model_dump(mode="json")


def _prepare_candidate_manifest_source(
    source: CandidateManifestGenerationSource,
    *,
    suite_path: Path,
    work_dir: Path,
) -> list[dict[str, Any]]:
    manifest_path = resolve_source_path(
        source.manifest.path,
        manifest_dir=suite_path.parent,
    )
    payload = stable_file_bytes(
        manifest_path,
        label=f"candidate manifest for {source.source_id!r}",
        expected_sha256=source.manifest.sha256,
        expected_size=source.manifest.size_bytes,
    )
    try:
        manifest = EvaluationCandidateManifest.model_validate(
            json.loads(payload.decode("utf-8"))
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationWorkspaceError(
            f"candidate manifest for {source.source_id!r} is not valid UTF-8 JSON"
        ) from exc
    output: list[dict[str, Any]] = []
    for row in manifest.candidates:
        artifacts: dict[str, Any] = {}
        for role, descriptor in sorted(row.artifacts.items()):
            destination = (
                work_dir
                / "artifacts"
                / "imports"
                / storage_name(source.source_id)
                / storage_name(row.system_id)
                / storage_name(row.case_id)
                / storage_name(row.sample_id)
                / f"{storage_name(role)}{Path(descriptor.path).suffix}"
            )
            copied = _copy_candidate_artifact(
                descriptor=descriptor,
                manifest_dir=manifest_path.parent,
                destination=destination,
                work_dir=work_dir,
                label=(
                    f"candidate {row.system_id!r}/{row.case_id!r}/"
                    f"{row.sample_id!r} artifact {role!r}"
                ),
            )
            artifacts[role] = copied.model_dump(mode="json")
        copied_row = row.model_copy(
            update={
                "artifacts": {
                    role: MaterializedArtifact.model_validate(descriptor)
                    for role, descriptor in artifacts.items()
                },
                "generator_provenance": {
                    **row.generator_provenance,
                    "source_kind": "candidate_manifest",
                    "source_id": source.source_id,
                },
            }
        )
        output.append(
            redact_persisted_value(copied_row.model_dump(mode="json"))
        )
    return output


def _archive_manifest_path(
    source: ArchivedModelGenerationSource,
    *,
    suite_path: Path,
) -> tuple[Path, Path]:
    archive_root = resolve_source_path(
        source.archive_root,
        manifest_dir=suite_path.parent,
    )
    if not archive_root.is_dir():
        raise EvaluationWorkspaceError(
            "The configured model archive is missing. Supply the required "
            f"artifacts at {source.archive_root!r}."
        )
    manifest_path = resolve_source_path(
        source.canonical_manifest,
        manifest_dir=archive_root,
        allow_absolute=False,
    )
    return archive_root, manifest_path


def _legacy_archive_candidate_rows(
    *,
    archive_root: Path,
    manifest_path: Path,
    source_id: str,
    suite: EvaluationSuite,
    work_dir: Path,
) -> list[dict[str, Any]]:
    payload = _load_json_file(
        manifest_path,
        label=f"archived model candidate manifest for {source_id!r}",
    )
    if not isinstance(payload, list):
        raise EvaluationWorkspaceError(
            "archived model canonical manifest must contain a JSON list"
        )
    view_by_profile = {
        view.system_id: view
        for view in suite.system_views
        if view.source_id == source_id
    }
    output: list[dict[str, Any]] = []
    for index, legacy in enumerate(payload, start=1):
        if not isinstance(legacy, dict):
            raise EvaluationWorkspaceError(
                f"archived model candidate row #{index} must be an object"
            )
        profile = str(legacy.get("profile") or "")
        view = view_by_profile.get(profile)
        if view is None:
            continue
        case_id = str(legacy.get("spec_id") or "").zfill(3)
        sample_id = str(legacy.get("generation_id") or "")
        checkpoint = str(legacy.get("checkpoint_label") or "")
        if checkpoint != view.checkpoint_or_view:
            continue
        model_value = str(legacy.get("generated_model_path") or "")
        if not model_value:
            raise EvaluationWorkspaceError(
                f"archived model row {profile}/{case_id}/{sample_id} has no model path"
            )
        model_source = resolve_source_path(
            model_value,
            manifest_dir=archive_root,
            allow_absolute=False,
        )
        destination = (
            work_dir
            / "artifacts"
            / "model-archive"
            / storage_name(profile)
            / storage_name(case_id)
            / storage_name(sample_id)
            / "model.json"
        )
        copied = materialize_artifact(
            ArtifactDescriptor(path=str(model_source)),
            manifest_dir=archive_root,
            destination=destination,
            work_dir=work_dir,
            label=f"archived model {profile}/{case_id}/{sample_id}",
        )
        output.append(
            CandidateRecord(
                system_id=profile,
                case_id=case_id,
                sample_id=sample_id,
                checkpoint_or_view=checkpoint,
                artifacts={"model": copied},
                generator_provenance={
                    "source_kind": "archived_models",
                    "source_id": source_id,
                    "provider": str(legacy.get("provider") or ""),
                    "model": str(legacy.get("model") or ""),
                },
            ).model_dump(mode="json")
        )
    return output


def _prepare_archived_models_source(
    source: ArchivedModelGenerationSource,
    *,
    suite: EvaluationSuite,
    suite_path: Path,
    work_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    archive_root, manifest_path = _archive_manifest_path(
        source,
        suite_path=suite_path,
    )
    candidates = _legacy_archive_candidate_rows(
        archive_root=archive_root,
        manifest_path=manifest_path,
        source_id=source.source_id,
        suite=suite,
        work_dir=work_dir,
    )
    return candidates, {
        "archive_root_name": archive_root.name,
        "canonical_manifest_sha256": manifest_sha256(
            _load_json_file(
                manifest_path,
                label="archived model canonical manifest",
            )
        ),
    }


def _generic_stored_results(
    *,
    source: StoredResultJudgeSource,
    suite_path: Path,
) -> list[dict[str, Any]] | None:
    manifest_path = resolve_source_path(
        source.manifest.path,
        manifest_dir=suite_path.parent,
    )
    payload = stable_file_bytes(
        manifest_path,
        label=f"stored judge-result manifest for {source.judge_id!r}",
        expected_sha256=source.manifest.sha256,
        expected_size=source.manifest.size_bytes,
    )
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvaluationWorkspaceError(
            f"stored judge-result manifest for {source.judge_id!r} is invalid"
        ) from exc
    if (
        not isinstance(decoded, dict)
        or decoded.get("artifact_kind")
        != "evaluation_judge_result_manifest"
    ):
        return None
    try:
        parsed = StoredJudgeResultManifest.model_validate(decoded)
    except ValueError as exc:
        raise EvaluationWorkspaceError(
            f"stored judge-result manifest for {source.judge_id!r} "
            "violates its declared schema"
        ) from exc
    return [
        redact_persisted_value(row.model_dump(mode="json"))
        for row in parsed.results
    ]


def _legacy_stored_results(
    *,
    source: StoredResultJudgeSource,
    suite_path: Path,
    work_dir: Path,
) -> list[dict[str, Any]]:
    manifest_path = resolve_source_path(
        source.manifest.path,
        manifest_dir=suite_path.parent,
    )
    archive_root = manifest_path.parent.parent
    payload = _load_json_file(
        manifest_path,
        label=f"archived judge manifest for {source.judge_id!r}",
    )
    if not isinstance(payload, list):
        raise EvaluationWorkspaceError(
            f"stored result manifest for {source.judge_id!r} has unsupported shape"
        )
    output: list[dict[str, Any]] = []
    for legacy in payload:
        if not isinstance(legacy, dict):
            continue
        system_id = str(legacy.get("profile") or "")
        case_id = str(legacy.get("spec_id") or "").zfill(3)
        sample_id = str(legacy.get("generation_id") or "")
        checkpoint = str(legacy.get("checkpoint_label") or "")
        judge_paths = legacy.get("judge_output_paths")
        if not isinstance(judge_paths, list):
            continue
        for repeat_index, raw_path in enumerate(judge_paths, start=1):
            source_path = resolve_source_path(
                str(raw_path),
                manifest_dir=archive_root,
                allow_absolute=False,
            )
            payload_bytes = stable_file_bytes(
                source_path,
                label=(
                    f"archived judge output {system_id}/{case_id}/"
                    f"{sample_id}/{repeat_index}"
                ),
            )
            destination = (
                work_dir
                / "artifacts"
                / "model-archive"
                / "judge-results"
                / storage_name(system_id)
                / storage_name(case_id)
                / storage_name(sample_id)
                / f"judge-{repeat_index:03d}.json"
            )
            write_bytes_atomic(destination, payload_bytes)
            archived_output = MaterializedArtifact(
                path=destination.relative_to(work_dir).as_posix(),
                media_type="application/json",
                schema_id="legacy-directional-judge-output",
                sha256=sha256_bytes(payload_bytes),
                size_bytes=len(payload_bytes),
            )
            try:
                evaluation = json.loads(payload_bytes.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise EvaluationWorkspaceError(
                    "archived directional judge output is invalid"
                ) from exc
            score = (
                evaluation.get("directional_semantic_score")
                if isinstance(evaluation, dict)
                else None
            )
            if not isinstance(score, dict):
                raise EvaluationWorkspaceError(
                    "archived directional judge output has no semantic score"
                )
            output.append(
                JudgeResultRecord(
                    result_id=(
                        f"{source.judge_id}:{system_id}:{case_id}:"
                        f"{sample_id}:{repeat_index}"
                    ),
                    judge_id=source.judge_id,
                    system_id=system_id,
                    case_id=case_id,
                    sample_id=sample_id,
                    checkpoint_or_view=checkpoint,
                    repeat_index=repeat_index,
                    status="completed",
                    details={
                        "directional_semantic_score": score,
                        "archived_output": archived_output.model_dump(
                            mode="json"
                        ),
                    },
                    usage=(
                        evaluation.get("judge_usage")
                        if isinstance(evaluation.get("judge_usage"), dict)
                        else None
                    ),
                ).model_dump(mode="json")
            )
    return output


def _prepare_stored_results(
    source: StoredResultJudgeSource,
    *,
    suite_path: Path,
    work_dir: Path,
) -> list[dict[str, Any]]:
    generic = _generic_stored_results(
        source=source,
        suite_path=suite_path,
    )
    if generic is not None:
        return generic
    return _legacy_stored_results(
        source=source,
        suite_path=suite_path,
        work_dir=work_dir,
    )


def _planned_counts(
    suite: EvaluationSuite,
    prepared_dataset: dict[str, Any],
    imported_candidates: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    case_count = len(prepared_dataset["cases"])
    generator_jobs = 0
    candidate_count = 0
    views_by_source: dict[str, int] = {}
    for view in suite.system_views:
        views_by_source[view.source_id] = views_by_source.get(view.source_id, 0) + 1
    for source in suite.generation_sources:
        if source.kind in {"catalog_harness", "command"}:
            generator_jobs += case_count * int(source.repetitions)
            candidate_count += (
                case_count
                * int(source.repetitions)
                * views_by_source.get(source.source_id, 0)
            )
        else:
            candidate_count += len(imported_candidates.get(source.source_id, []))
    judge_jobs = sum(
        candidate_count * int(judge.repetitions) for judge in suite.judges
    )
    return {
        "case_count": case_count,
        "planned_generator_jobs": generator_jobs,
        "planned_candidates": candidate_count,
        "planned_judge_jobs": judge_jobs,
    }


def _validate_prepared_domain_references(
    *,
    suite: EvaluationSuite,
    prepared_dataset: dict[str, Any],
    imported_candidates: dict[str, list[dict[str, Any]]],
    imported_results: dict[str, list[dict[str, Any]]],
    claims: dict[str, Any] | None,
) -> None:
    case_ids = {
        str(case.get("case_id"))
        for case in prepared_dataset.get("cases", [])
        if isinstance(case, dict) and case.get("case_id")
    }
    views_by_system = {view.system_id: view for view in suite.system_views}
    imported_identities: set[tuple[str, str, str, str]] = set()
    for source_id, rows in imported_candidates.items():
        for payload in rows:
            candidate = CandidateRecord.model_validate(payload)
            view = views_by_system.get(candidate.system_id)
            if (
                view is None
                or view.source_id != source_id
                or view.checkpoint_or_view != candidate.checkpoint_or_view
            ):
                raise EvaluationWorkspaceError(
                    f"imported candidate {candidate.system_id!r}/"
                    f"{candidate.case_id!r}/{candidate.sample_id!r} does not "
                    "match a declared system view for its source"
                )
            if candidate.case_id not in case_ids:
                raise EvaluationWorkspaceError(
                    f"imported candidate references unknown case "
                    f"{candidate.case_id!r}"
                )
            missing_roles = sorted(
                set(view.artifact_roles) - set(candidate.artifacts)
            )
            if missing_roles:
                raise EvaluationWorkspaceError(
                    f"imported candidate {candidate.system_id!r} lacks declared "
                    "artifact roles: " + ", ".join(missing_roles)
                )
            imported_identities.add(
                (
                    candidate.system_id,
                    candidate.case_id,
                    candidate.sample_id,
                    candidate.checkpoint_or_view,
                )
            )
    metric_definitions = {metric.metric_id: metric for metric in suite.metrics}
    judges_by_id = {judge.judge_id: judge for judge in suite.judges}
    stored_result_ids: set[str] = set()
    stored_result_identities: set[tuple[str, str, str, str, str, int]] = set()
    for judge_id, rows in imported_results.items():
        if judge_id not in judges_by_id:
            raise EvaluationWorkspaceError(
                f"stored results reference unknown judge {judge_id!r}"
            )
        for payload in rows:
            result = JudgeResultRecord.model_validate(payload)
            identity_with_repeat = (
                result.judge_id,
                result.system_id,
                result.case_id,
                result.sample_id,
                result.checkpoint_or_view,
                result.repeat_index,
            )
            if (
                result.result_id in stored_result_ids
                or identity_with_repeat in stored_result_identities
            ):
                raise EvaluationWorkspaceError(
                    f"stored result {result.result_id!r} has a duplicate identity"
                )
            stored_result_ids.add(result.result_id)
            stored_result_identities.add(identity_with_repeat)
            view = views_by_system.get(result.system_id)
            if (
                result.judge_id != judge_id
                or view is None
                or view.checkpoint_or_view != result.checkpoint_or_view
                or result.case_id not in case_ids
                or result.repeat_index > judges_by_id[judge_id].repetitions
            ):
                raise EvaluationWorkspaceError(
                    f"stored result {result.result_id!r} does not match the "
                    "declared judge, dataset, and system views"
                )
            identity = (
                result.system_id,
                result.case_id,
                result.sample_id,
                result.checkpoint_or_view,
            )
            if view.source_id in imported_candidates and identity not in (
                imported_identities
            ):
                raise EvaluationWorkspaceError(
                    f"stored result {result.result_id!r} has no imported candidate"
                )
            unknown_metrics = sorted(
                set(result.metrics) - set(metric_definitions)
            )
            if unknown_metrics:
                raise EvaluationWorkspaceError(
                    f"stored result {result.result_id!r} contains undeclared "
                    "metrics: " + ", ".join(unknown_metrics)
                )
            for metric_id, value in result.metrics.items():
                definition = metric_definitions[metric_id]
                if definition.minimum is not None and value < definition.minimum:
                    raise EvaluationWorkspaceError(
                        f"stored result metric {metric_id!r} is below its minimum"
                    )
                if definition.maximum is not None and value > definition.maximum:
                    raise EvaluationWorkspaceError(
                        f"stored result metric {metric_id!r} exceeds its maximum"
                    )
    if claims is None:
        return
    parsed_claims = EvaluationClaimsManifest.model_validate(claims)
    comparison_ids = {
        comparison.comparison_id for comparison in suite.comparisons
    }
    declared_judge_ids = {judge.judge_id for judge in suite.judges}
    allowed_metrics = {
        *metric_definitions,
        "candidate_count",
        "complete_candidate_count",
        "failed_candidate_count",
        "case_count",
        "gold_count",
        "predicted_count",
        "represented_gold_count",
        "supported_predicted_count",
        "micro_precision",
        "micro_recall",
        "micro_f1",
        "median_precision",
        "median_recall",
    }
    allowed_metrics.update(
        f"{kind}_{metric}"
        for kind in ("entity", "attribute", "relationship", "identifier")
        for metric in (
            "gold_count",
            "predicted_count",
            "represented_gold_count",
            "supported_predicted_count",
            "micro_precision",
            "micro_recall",
            "micro_f1",
            "median_precision",
            "median_recall",
        )
    )
    for claim in parsed_claims.expanded_claims():
        if claim.system_id is not None and claim.system_id not in views_by_system:
            raise EvaluationWorkspaceError(
                f"claim {claim.claim_id!r} references unknown system"
            )
        if (
            claim.comparison_id is not None
            and claim.comparison_id not in comparison_ids
        ):
            raise EvaluationWorkspaceError(
                f"claim {claim.claim_id!r} references unknown comparison"
            )
        if claim.judge_id is not None and claim.judge_id not in (
            declared_judge_ids
        ):
            raise EvaluationWorkspaceError(
                f"claim {claim.claim_id!r} references unknown judge"
            )
        if claim.judge_id is None and len(declared_judge_ids) > 1:
            raise EvaluationWorkspaceError(
                f"claim {claim.claim_id!r} must select a judge in a "
                "multi-judge suite"
            )
        if claim.metric_id not in allowed_metrics:
            raise EvaluationWorkspaceError(
                f"claim {claim.claim_id!r} references unknown metric"
            )


def _verify_prepared_dataset(
    prepared_dataset: dict[str, Any],
    *,
    work_dir: Path,
) -> None:
    EvaluationDataset  # retain an explicit domain dependency for boundary checks
    for case in prepared_dataset.get("cases", []):
        for category in ("inputs", "references"):
            artifacts = case.get(category) if isinstance(case, dict) else None
            if not isinstance(artifacts, dict):
                raise EvaluationWorkspaceError(
                    "prepared dataset artifact map is invalid"
                )
            for descriptor in artifacts.values():
                verify_materialized_artifact(descriptor, work_dir=work_dir)


def _verify_prepared_imports(
    prepared: dict[str, Any],
    *,
    work_dir: Path,
) -> None:
    imported = prepared.get("imported_candidates")
    if not isinstance(imported, dict):
        raise EvaluationWorkspaceError("prepared imported-candidate map is invalid")
    for rows in imported.values():
        if not isinstance(rows, list):
            raise EvaluationWorkspaceError(
                "prepared imported-candidate rows are invalid"
            )
        for row in rows:
            candidate = CandidateRecord.model_validate(row)
            for artifact in candidate.artifacts.values():
                verify_materialized_artifact(artifact, work_dir=work_dir)
    imported_results = prepared.get("imported_results")
    if not isinstance(imported_results, dict):
        raise EvaluationWorkspaceError(
            "prepared imported-result map is invalid"
        )
    for rows in imported_results.values():
        if not isinstance(rows, list):
            raise EvaluationWorkspaceError(
                "prepared imported-result rows are invalid"
            )
        for row in rows:
            result = JudgeResultRecord.model_validate(row)
            archived_output = result.details.get("archived_output")
            if isinstance(archived_output, dict):
                verify_materialized_artifact(
                    archived_output,
                    work_dir=work_dir,
                )
    source_manifests = prepared.get("source_manifests")
    if not isinstance(source_manifests, dict):
        raise EvaluationWorkspaceError(
            "prepared source-manifest map is invalid"
        )
    for descriptor in source_manifests.values():
        verify_materialized_artifact(
            descriptor,
            work_dir=work_dir,
        )


def _validate_existing_prepared(
    *,
    suite: EvaluationSuite,
    work_dir: Path,
    prepared_path: Path,
) -> dict[str, Any]:
    payload = _load_json_file(prepared_path, label="prepared evaluation suite")
    if not isinstance(payload, dict):
        raise EvaluationWorkspaceError("prepared evaluation suite must be an object")
    expected = suite_declaration_sha256(suite)
    if payload.get("suite_declaration_sha256") != expected:
        raise EvaluationWorkspaceError(
            "evaluation suite declaration does not match the resumable work directory"
        )
    recorded_build = payload.get("build_identity")
    current_build = current_build_identity().detached_dict()
    if (
        not isinstance(recorded_build, dict)
        or recorded_build.get("canonical_sha256")
        != current_build.get("canonical_sha256")
    ):
        raise EvaluationWorkspaceError(
            "executable build identity does not match the resumable work directory"
        )
    _verify_prepared_dataset(payload.get("dataset") or {}, work_dir=work_dir)
    _verify_prepared_imports(payload, work_dir=work_dir)
    _validate_prepared_domain_references(
        suite=suite,
        prepared_dataset=payload.get("dataset") or {},
        imported_candidates=payload.get("imported_candidates") or {},
        imported_results=payload.get("imported_results") or {},
        claims=payload.get("claims"),
    )
    return payload


def prepare_workspace(
    *,
    suite: EvaluationSuite,
    suite_path: Path,
    work_dir: Path,
    resume: bool,
    mode: str,
) -> dict[str, Any]:
    _validate_catalog_sources(suite)
    _validate_directional_judges(suite)
    prepared_path = work_dir / PREPARED_SUITE_FILENAME
    state_path = work_dir / RUN_STATE_FILENAME
    marker_path = work_dir / PREPARATION_MARKER_FILENAME
    if prepared_path.exists():
        if not resume:
            raise EvaluationWorkspaceError(
                "work directory already contains an evaluation; use --resume"
            )
        prepared = _validate_existing_prepared(
            suite=suite,
            work_dir=work_dir,
            prepared_path=prepared_path,
        )
        if marker_path.exists():
            _validate_preparation_marker(
                suite=suite,
                marker_path=marker_path,
            )
        if not state_path.exists():
            if not marker_path.exists():
                raise EvaluationWorkspaceError(
                    "prepared evaluation is missing its canonical run state"
                )
            write_json_atomic(
                state_path,
                _initial_run_state(
                    suite=suite,
                    prepared=prepared,
                    mode=mode,
                ),
            )
        marker_path.unlink(missing_ok=True)
        return prepared
    if work_dir.exists() and any(work_dir.iterdir()):
        if not resume or not marker_path.is_file():
            raise EvaluationWorkspaceError(
                "work directory must be empty or contain an exactly resumable evaluation"
            )
        _validate_preparation_marker(
            suite=suite,
            marker_path=marker_path,
        )
        unexpected = sorted(
            path.name
            for path in work_dir.iterdir()
            if path.name not in {
                PREPARATION_MARKER_FILENAME,
                "artifacts",
            }
        )
        if unexpected:
            raise EvaluationWorkspaceError(
                "partial evaluation preparation contains unexpected state"
            )
    work_dir.mkdir(parents=True, exist_ok=True)
    if not marker_path.exists():
        write_json_atomic(marker_path, _preparation_marker(suite))
    dataset_path = _dataset_path(suite, suite_path)
    prepared_dataset = prepare_dataset(dataset_path, work_dir=work_dir)
    source_manifests: dict[str, dict[str, Any]] = {
        "dataset": _materialize_source_manifest(
            ArtifactDescriptor(path=str(dataset_path)),
            manifest_dir=dataset_path.parent,
            destination=work_dir / "artifacts" / "manifests" / "dataset.json",
            work_dir=work_dir,
            label="evaluation dataset manifest",
            schema_id="evaluation_dataset-v1",
        )
    }
    imported_candidates: dict[str, list[dict[str, Any]]] = {}
    import_metadata: dict[str, Any] = {}
    for source in suite.generation_sources:
        if source.kind == "candidate_manifest":
            source_manifests[f"generator:{source.source_id}"] = (
                _materialize_source_manifest(
                    source.manifest,
                    manifest_dir=suite_path.parent,
                    destination=(
                        work_dir
                        / "artifacts"
                        / "manifests"
                        / f"generator-{storage_name(source.source_id)}.json"
                    ),
                    work_dir=work_dir,
                    label=(
                        f"candidate manifest for {source.source_id!r}"
                    ),
                    schema_id="evaluation_candidate_manifest-v1",
                )
            )
            imported_candidates[source.source_id] = (
                _prepare_candidate_manifest_source(
                    source,
                    suite_path=suite_path,
                    work_dir=work_dir,
                )
            )
        elif source.kind == "archived_models":
            rows, metadata = _prepare_archived_models_source(
                source,
                suite=suite,
                suite_path=suite_path,
                work_dir=work_dir,
            )
            archive_root, archive_manifest = _archive_manifest_path(
                source,
                suite_path=suite_path,
            )
            del archive_root
            source_manifests[f"generator:{source.source_id}"] = (
                _materialize_source_manifest(
                    ArtifactDescriptor(path=str(archive_manifest)),
                    manifest_dir=archive_manifest.parent,
                    destination=(
                        work_dir
                        / "artifacts"
                        / "manifests"
                        / f"generator-{storage_name(source.source_id)}.json"
                    ),
                    work_dir=work_dir,
                    label=(
                        f"archived candidate manifest for "
                        f"{source.source_id!r}"
                    ),
                    schema_id="legacy-candidate-manifest",
                )
            )
            imported_candidates[source.source_id] = rows
            import_metadata[source.source_id] = metadata
    imported_results: dict[str, list[dict[str, Any]]] = {}
    for judge in suite.judges:
        if judge.kind == "stored_result_manifest":
            source_manifests[f"judge:{judge.judge_id}"] = (
                _materialize_source_manifest(
                    judge.manifest,
                    manifest_dir=suite_path.parent,
                    destination=(
                        work_dir
                        / "artifacts"
                        / "manifests"
                        / f"judge-{storage_name(judge.judge_id)}.json"
                    ),
                    work_dir=work_dir,
                    label=(
                        f"stored judge-result manifest for "
                        f"{judge.judge_id!r}"
                    ),
                    schema_id=(
                        judge.manifest.schema_id
                        or "evaluation_judge_result_manifest-v1"
                    ),
                )
            )
            imported_results[judge.judge_id] = _prepare_stored_results(
                judge,
                suite_path=suite_path,
                work_dir=work_dir,
            )
    claims = None
    claims_path = _claims_path(suite, suite_path)
    if claims_path is not None:
        claims = load_claims(claims_path).model_dump(mode="json")
        source_manifests["claims"] = _materialize_source_manifest(
            ArtifactDescriptor(path=str(claims_path)),
            manifest_dir=claims_path.parent,
            destination=work_dir / "artifacts" / "manifests" / "claims.json",
            work_dir=work_dir,
            label="evaluation claims manifest",
            schema_id="evaluation_claims-v1",
        )
    _validate_prepared_domain_references(
        suite=suite,
        prepared_dataset=prepared_dataset,
        imported_candidates=imported_candidates,
        imported_results=imported_results,
        claims=claims,
    )
    plan = _planned_counts(suite, prepared_dataset, imported_candidates)
    prepared = {
        "artifact_kind": "prepared_evaluation_suite",
        "schema_version": 1,
        "suite_declaration_sha256": suite_declaration_sha256(suite),
        "suite": _safe_suite_summary(suite),
        "dataset": prepared_dataset,
        "source_manifests": source_manifests,
        "imported_candidates": imported_candidates,
        "imported_results": imported_results,
        "import_metadata": import_metadata,
        "claims": claims,
        "plan": plan,
        "mode": mode,
        "build_identity": current_build_identity().detached_dict(),
    }
    prepared["prepared_sha256"] = manifest_sha256(prepared)
    write_json_atomic(prepared_path, prepared)
    write_json_atomic(
        state_path,
        _initial_run_state(
            suite=suite,
            prepared=prepared,
            mode=mode,
        ),
    )
    marker_path.unlink(missing_ok=True)
    return prepared


def load_run_state(work_dir: Path) -> dict[str, Any]:
    path = work_dir / RUN_STATE_FILENAME
    payload = _load_json_file(path, label="evaluation run state")
    if not isinstance(payload, dict):
        raise EvaluationWorkspaceError("evaluation run state must be an object")
    return payload


def update_run_state(work_dir: Path, state: dict[str, Any]) -> None:
    write_json_atomic(work_dir / RUN_STATE_FILENAME, state)


def _output_hashes(work_dir: Path, relative_paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative_value in relative_paths:
        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts:
            raise EvaluationWorkspaceError("stage output path is unsafe")
        path = work_dir / relative
        hashes[relative.as_posix()] = sha256_bytes(path.read_bytes())
    return hashes


def stage_is_resumable(
    *,
    work_dir: Path,
    state: dict[str, Any],
    stage_name: str,
) -> bool:
    stage = (state.get("stages") or {}).get(stage_name)
    if not isinstance(stage, dict) or stage.get("status") != "completed":
        return False
    outputs = stage.get("outputs")
    if not isinstance(outputs, dict):
        raise EvaluationWorkspaceError(
            f"completed stage {stage_name!r} has no output hashes"
        )
    for relative_value, expected_hash in outputs.items():
        relative = Path(str(relative_value))
        if relative.is_absolute() or ".." in relative.parts:
            raise EvaluationWorkspaceError(
                f"stage {stage_name!r} contains an unsafe output path"
            )
        path = work_dir / relative
        if not path.is_file():
            raise EvaluationWorkspaceError(
                f"stage {stage_name!r} output is missing"
            )
        actual = sha256_bytes(path.read_bytes())
        if actual != expected_hash:
            raise EvaluationWorkspaceError(
                f"stage {stage_name!r} output conflicts with resumable state"
            )
    return True


def complete_stage(
    *,
    work_dir: Path,
    state: dict[str, Any],
    stage_name: str,
    relative_outputs: list[str],
) -> None:
    stages = state.setdefault("stages", {})
    stages[stage_name] = {
        "status": "completed",
        "outputs": _output_hashes(work_dir, relative_outputs),
    }
    state["status"] = stage_name
    update_run_state(work_dir, state)


def reset_failed_work_directory(work_dir: Path) -> None:
    """Test helper for pre-publication failures; never used by the CLI."""

    shutil.rmtree(work_dir)


__all__ = [
    "EvaluationWorkspaceError",
    "PREPARATION_MARKER_FILENAME",
    "PREPARED_SUITE_FILENAME",
    "RUN_STATE_FILENAME",
    "complete_stage",
    "load_claims",
    "load_run_state",
    "load_suite",
    "prepare_workspace",
    "stage_is_resumable",
    "suite_declaration_sha256",
    "update_run_state",
]
