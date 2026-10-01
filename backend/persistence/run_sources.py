from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.api.settings import RUN_RECORD_FILENAME
from backend.persistence.common import read_json_file
from backend.persistence.result_records import read_result_record
from backend.persistence.run_record_integrity import read_canonical_run_record
from backend.persistence.run_paths import safe_run_dir
from core.schemas import StructuredModel, validate_structured_model_links
from backend.persistence.run_specifications import read_sealed_run_specification


def source_run_record(
    source_job_id: str,
    *,
    runs_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    source_run_dir = safe_run_dir(source_job_id, runs_dir=runs_dir)
    record_path = source_run_dir / RUN_RECORD_FILENAME
    if not record_path.is_file():
        raise FileNotFoundError("Source run not found.")
    record = read_canonical_run_record(record_path, runs_dir=runs_dir)
    return source_run_dir, record


def source_run_specification(source_run_dir: Path, record: dict[str, Any]) -> str:
    return read_sealed_run_specification(source_run_dir, record)


def structured_model_from_run_dir(run_dir: Path) -> StructuredModel | None:
    result_path = run_dir / "result.json"
    if result_path.is_file():
        result_payload = read_result_record(run_dir)
        structured_payload = result_payload.get("structured_model")
        if isinstance(structured_payload, dict):
            model = StructuredModel.model_validate(structured_payload)
            validate_structured_model_links(model)
            return model

    structured_model_path = run_dir / "structured_model.json"
    if not structured_model_path.is_file():
        return None
    try:
        model = StructuredModel.model_validate(read_json_file(structured_model_path))
        validate_structured_model_links(model)
        return model
    except (OSError, json.JSONDecodeError, ValueError):
        return None
