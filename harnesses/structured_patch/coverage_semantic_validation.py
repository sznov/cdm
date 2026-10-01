from __future__ import annotations

from typing import Any

from core.json_parsing import parse_json_object_output
from core.schemas import StructuredOutputError


def parse_semantic_patch_validation_output(raw_output: str) -> dict[str, Any]:
    payload = parse_json_object_output(raw_output, label="Semantic patch validator")
    decision = str(payload.get("decision") or payload.get("verdict") or "").strip().lower()
    if decision not in {"accept", "reject"}:
        raise StructuredOutputError("Semantic patch validator decision must be 'accept' or 'reject'.")
    raw_problems = payload.get("problems") or []
    if isinstance(raw_problems, str):
        raw_problems = [raw_problems]
    if not isinstance(raw_problems, list):
        raw_problems = []
    return {
        "decision": decision,
        "accepted": decision == "accept",
        "reason": str(payload.get("reason") or "").strip(),
        "evidence": str(payload.get("evidence") or "").strip(),
        "problems": [str(problem).strip() for problem in raw_problems if str(problem).strip()],
        "retry_instruction": str(payload.get("retry_instruction") or payload.get("retryInstruction") or "").strip(),
    }


__all__ = ["parse_semantic_patch_validation_output"]
