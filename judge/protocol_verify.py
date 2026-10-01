from __future__ import annotations

from pathlib import Path
from typing import Any

from core.artifacts import load_json, read_checkpoint_manifest_path
from judge.protocol_profiles import protocol_profiles


def spec_ids_from_dir(spec_dir: Path, requested: list[str] | None = None) -> list[str]:
    if requested:
        return sorted({str(spec_id).zfill(3) for spec_id in requested})
    return sorted(path.stem.zfill(3) for path in spec_dir.glob("*.txt"))


def _load_list(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON list: {path}")
    return [row for row in payload if isinstance(row, dict)]


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("spec_id") or "").zfill(3),
        str(row.get("generation_run_id") or row.get("generation_id") or ""),
        str(row.get("checkpoint_label") or ""),
    )


def _path_exists(row: dict[str, Any], *keys: str) -> bool:
    value = next((row.get(key) for key in keys if row.get(key)), "")
    return bool(value) and Path(str(value)).exists()


def _profile_expected_generations(profile: dict[str, Any], default_expected_generations: int | None) -> int:
    value = (
        default_expected_generations
        or profile.get("expected_generations")
        or profile.get("target_valid_generations")
        or profile.get("generation_repeats")
        or 1
    )
    return int(value)


def _judge_completion_counts(judge_dir: Path) -> dict[tuple[str, str, str], int]:
    manifest_path = judge_dir / "judge_run_manifest.json"
    if not manifest_path.exists():
        return {}
    rows = _load_list(manifest_path)
    counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        if row.get("status") != "completed":
            continue
        key = _row_key(row)
        counts[key] = counts.get(key, 0) + 1
    return counts


def verify_protocol_artifact(
    *,
    protocol_dir: Path,
    profile_config: dict[str, Any],
    spec_ids: list[str],
    default_expected_generations: int | None = None,
    default_expected_judge_repeats: int | None = None,
    verify_judges: bool = True,
) -> list[str]:
    errors: list[str] = []
    for profile in protocol_profiles(profile_config):
        profile_id = str(profile["id"])
        manifest_value = profile.get("manifest")
        if not manifest_value:
            errors.append(f"{profile_id}: missing manifest path in profile config")
            continue
        manifest_path = protocol_dir / str(manifest_value)
        if not manifest_path.exists():
            if profile.get("optional"):
                continue
            errors.append(f"{profile_id}: missing checkpoint manifest {manifest_path}")
            continue
        rows = read_checkpoint_manifest_path(manifest_path)
        checkpoint_labels = set(profile.get("checkpoint_labels") or [])
        if checkpoint_labels:
            rows = [row for row in rows if str(row.get("checkpoint_label") or "") in checkpoint_labels]
        expected_generations = _profile_expected_generations(profile, default_expected_generations)
        seen_keys: set[tuple[str, str, str]] = set()
        duplicate_keys: set[tuple[str, str, str]] = set()
        rows_by_spec: dict[str, list[dict[str, Any]]] = {spec_id: [] for spec_id in spec_ids}
        for row in rows:
            key = _row_key(row)
            if key in seen_keys:
                duplicate_keys.add(key)
            seen_keys.add(key)
            spec_id = key[0]
            if spec_id in rows_by_spec:
                rows_by_spec[spec_id].append(row)
            if not _path_exists(row, "model_path", "generated_model_path"):
                errors.append(f"{profile_id}: missing generated model for row {key}")
            if not _path_exists(row, "gold_path", "reference_model_path"):
                errors.append(f"{profile_id}: missing reference model for row {key}")
            if row.get("spec_path") and not Path(str(row["spec_path"])).exists():
                errors.append(f"{profile_id}: missing specification file for row {key}")
            if row.get("plantuml_path") and not Path(str(row["plantuml_path"])).exists():
                errors.append(f"{profile_id}: missing PlantUML file for row {key}")
        for key in sorted(duplicate_keys):
            errors.append(f"{profile_id}: duplicate canonical row key {key}")
        for spec_id, spec_rows in sorted(rows_by_spec.items()):
            if len(spec_rows) != expected_generations:
                errors.append(
                    f"{profile_id}: spec {spec_id} has {len(spec_rows)} row(s), expected {expected_generations}"
                )
        if verify_judges:
            judge_output_dir = profile.get("judge_output_dir")
            if not judge_output_dir:
                errors.append(f"{profile_id}: missing judge_output_dir in profile config")
                continue
            judge_counts = _judge_completion_counts(protocol_dir / str(judge_output_dir))
            expected_repeats = int(default_expected_judge_repeats or profile.get("judge_repeats") or 5)
            for row in rows:
                key = _row_key(row)
                completed = judge_counts.get(key, 0)
                if completed < expected_repeats:
                    errors.append(
                        f"{profile_id}: row {key} has {completed} completed judge output(s), expected at least {expected_repeats}"
                    )
    return errors


__all__ = ["spec_ids_from_dir", "verify_protocol_artifact"]
