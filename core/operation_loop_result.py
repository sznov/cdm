from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.atomic_io import atomic_write_text
from core.artifact_versions import add_result_record_version
from core.config_safety import redact_persisted_value, redact_sensitive_text
from core.schemas import OperationLoopWorkingModel, StructuredModel


@dataclass
class OperationLoopResult:
    job_id: str
    working_model: OperationLoopWorkingModel
    structured_model: StructuredModel
    plantuml: str
    plantuml_url: str
    operation_history: list[dict[str, Any]]
    input_prompts: list[dict[str, Any]]
    completion_checks: list[dict[str, Any]]
    plan_updates: list[dict[str, Any]]
    model_call_log_dir: str | None
    model_call_logs: list[dict[str, Any]]
    iterations: int
    accepted_operation_count: int
    rejected_operation_count: int
    stop_reason: str
    model: str
    usage_steps: list[dict[str, Any] | None] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return add_result_record_version({
            "job_id": self.job_id,
            "working_model": self.working_model.model_dump(mode="json"),
            "structured_model": self.structured_model.model_dump(mode="json"),
            "plantuml": self.plantuml,
            "plantuml_url": self.plantuml_url,
            "operation_history": self.operation_history,
            "input_prompts": self.input_prompts,
            "completion_checks": self.completion_checks,
            "plan_updates": self.plan_updates,
            "model_call_log_dir": self.model_call_log_dir,
            "model_call_logs": self.model_call_logs,
            "iterations": self.iterations,
            "accepted_operation_count": self.accepted_operation_count,
            "rejected_operation_count": self.rejected_operation_count,
            "stop_reason": self.stop_reason,
            "model": self.model,
            "usage_steps": self.usage_steps,
        })


def write_json_file(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def write_result(result: OperationLoopResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_result = redact_persisted_value(result.to_dict())
    if not isinstance(safe_result, dict):  # pragma: no cover - result object contract
        raise TypeError("Result redaction must preserve its object shape.")
    # Inspectable views are derived from the complete result. Publish them
    # first so result.json remains the canonical commit point.
    atomic_write_text(
        output_dir / "final.plantuml",
        redact_sensitive_text(
            safe_result["plantuml"],
            redact_named_values=False,
            redact_url_fragments=False,
        ),
    )
    write_json_file(output_dir / "working_model.json", safe_result["working_model"])
    write_json_file(output_dir / "structured_model.json", safe_result["structured_model"])
    write_json_file(output_dir / "operation_history.json", safe_result["operation_history"])
    write_json_file(output_dir / "input_prompts.json", safe_result["input_prompts"])
    write_json_file(output_dir / "result.json", safe_result)


__all__ = ["OperationLoopResult", "write_result"]
