from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.persistence.common import read_json_file, write_json_file
from backend.persistence.locks import run_lock
from backend.persistence.post_run_transaction_guard import (
    require_post_run_mutation_allowed,
)
from core.artifact_versions import add_result_record_version, normalize_result_payload
from core.atomic_io import atomic_write_text
from core.plantuml_structured import render_structured_model_to_plantuml
from core.schemas import StructuredModel, validate_structured_model_links
from harnesses.structured_patch.model_conversion import structured_model_to_working_model


RESULT_RECORD_FILENAME = "result.json"
_JSON_DERIVED_ARTIFACTS = {
    "structured_model": "structured_model.json",
    "working_model": "working_model.json",
    "operation_history": "operation_history.json",
    "input_prompts": "input_prompts.json",
}


def _complete_model_views(payload: dict[str, Any]) -> dict[str, Any]:
    completed = dict(payload)
    structured_payload = completed.get("structured_model")
    if not isinstance(structured_payload, dict):
        return completed

    model = StructuredModel.model_validate(structured_payload)
    validate_structured_model_links(model)
    completed["structured_model"] = model.model_dump(mode="json")
    if not isinstance(completed.get("working_model"), dict):
        completed["working_model"] = structured_model_to_working_model(model).model_dump(mode="json")
    if not isinstance(completed.get("plantuml"), str) or not completed.get("plantuml"):
        completed["plantuml"] = render_structured_model_to_plantuml(model)
    if not isinstance(completed.get("plantuml_url"), str):
        completed["plantuml_url"] = ""
    return completed


def prepare_result_record_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return one complete, versioned result payload without publishing it."""

    return add_result_record_version(_complete_model_views(payload))


def result_derived_artifact_values(
    payload: dict[str, Any],
) -> dict[str, dict[str, Any] | list[Any] | str]:
    """Return the inspectable artifacts derived from a prepared result."""

    artifacts: dict[str, dict[str, Any] | list[Any] | str] = {}
    for key, filename in _JSON_DERIVED_ARTIFACTS.items():
        value = payload.get(key)
        if isinstance(value, (dict, list)):
            artifacts[filename] = value
    plantuml = payload.get("plantuml")
    if isinstance(plantuml, str):
        artifacts["final.plantuml"] = plantuml
    return artifacts


def read_result_record(run_dir: Path) -> dict[str, Any]:
    """Read the canonical current result and require this release's schema."""

    return normalize_result_payload(read_json_file(run_dir / RESULT_RECORD_FILENAME))


def validate_result_record(run_dir: Path) -> dict[str, Any]:
    """Validate the canonical result and every model-derived view without writing."""

    return _complete_model_views(read_result_record(run_dir))


def _write_derived_result_artifacts(run_dir: Path, payload: dict[str, Any]) -> None:
    for filename, value in result_derived_artifact_values(payload).items():
        if isinstance(value, (dict, list)):
            write_json_file(run_dir / filename, value)
        else:
            atomic_write_text(run_dir / filename, value)


def write_result_record(run_dir: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Publish a complete result, using ``result.json`` as the commit point.

    Inspectable model views are written first. If the process stops between a
    derived write and the final replacement, startup reconciliation rebuilds
    every view from the still-authoritative result record.
    """

    with run_lock(run_dir):
        require_post_run_mutation_allowed(run_dir)
        completed = prepare_result_record_payload(payload)
        _write_derived_result_artifacts(run_dir, completed)
        write_json_file(run_dir / RESULT_RECORD_FILENAME, completed)
        return completed


def update_result_record(run_dir: Path, **changes: Any) -> dict[str, Any]:
    with run_lock(run_dir):
        require_post_run_mutation_allowed(run_dir)
        payload = read_result_record(run_dir)
        payload.update(changes)
        return write_result_record(run_dir, payload)


def _json_artifact_matches(path: Path, expected: dict[str, Any] | list[Any]) -> bool:
    try:
        return json.loads(path.read_text(encoding="utf-8")) == expected
    except (OSError, json.JSONDecodeError):
        return False


def reconcile_derived_result_artifacts(run_dir: Path) -> list[str]:
    """Rebuild stale/missing inspectable views from canonical ``result.json``."""

    result_path = run_dir / RESULT_RECORD_FILENAME
    if not result_path.is_file():
        return []
    with run_lock(run_dir):
        payload = _complete_model_views(read_result_record(run_dir))
        rebuilt: list[str] = []
        for key, filename in _JSON_DERIVED_ARTIFACTS.items():
            value = payload.get(key)
            path = run_dir / filename
            if isinstance(value, (dict, list)) and not _json_artifact_matches(path, value):
                write_json_file(path, value)
                rebuilt.append(filename)
        plantuml = payload.get("plantuml")
        plantuml_path = run_dir / "final.plantuml"
        if isinstance(plantuml, str):
            try:
                matches = plantuml_path.read_text(encoding="utf-8") == plantuml
            except OSError:
                matches = False
            if not matches:
                atomic_write_text(plantuml_path, plantuml)
                rebuilt.append(plantuml_path.name)

        # A result created before all model views were populated is completed
        # only after its derived files are safe. This remains the commit point.
        if payload != read_result_record(run_dir):
            write_json_file(result_path, add_result_record_version(payload))
        return rebuilt


__all__ = [
    "RESULT_RECORD_FILENAME",
    "prepare_result_record_payload",
    "read_result_record",
    "reconcile_derived_result_artifacts",
    "result_derived_artifact_values",
    "update_result_record",
    "validate_result_record",
    "write_result_record",
]
