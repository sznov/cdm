from __future__ import annotations

from typing import Any

from core.json_parsing import parse_json_object_output
from harnesses.structured_patch.coverage_decision_patches import normalize_decision_patch_payload
from core.schemas import StructuredOutputError


def parse_plan_coverage_findings_output(raw_output: str) -> list[dict[str, str]]:
    payload = parse_json_object_output(raw_output, label="Plan coverage critic")
    return parse_plan_coverage_payload(payload)["findings"]


def parse_plan_coverage_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_findings = payload.get("findings", [])
    if raw_findings is None:
        raw_findings = []
    if not isinstance(raw_findings, list):
        raise StructuredOutputError("Plan coverage critic output must contain a findings list.")
    findings: list[dict[str, str]] = []
    for index, item in enumerate(raw_findings, start=1):
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or "").strip()
        suggested_change = str(item.get("suggested_change") or item.get("suggestedChange") or "").strip()
        if not summary and not suggested_change:
            continue
        findings.append(
            {
                "id": str(item.get("id") or f"F{index}").strip() or f"F{index}",
                "severity": str(item.get("severity") or "medium").strip().lower(),
                "kind": str(item.get("kind") or "other").strip(),
                "plan_task_id": str(item.get("plan_task_id") or item.get("planTaskId") or "").strip(),
                "summary": summary,
                "evidence": str(item.get("evidence") or "").strip(),
                "suggested_change": suggested_change,
            }
        )
    raw_decision_patches = payload.get("decision_patches") or payload.get("decisionPatches") or []
    if raw_decision_patches is None:
        raw_decision_patches = []
    if not isinstance(raw_decision_patches, list):
        raw_decision_patches = []
    decision_patches: list[dict[str, Any]] = []
    for index, item in enumerate(raw_decision_patches, start=1):
        if not isinstance(item, dict):
            continue
        normalized = normalize_decision_patch_payload(item, index=index)
        if normalized is not None:
            decision_patches.append(normalized)
    return {"findings": findings, "decision_patches": decision_patches}


__all__ = ["parse_plan_coverage_findings_output", "parse_plan_coverage_payload"]
