from __future__ import annotations

import json
import re
from typing import Any

from core.json_repair_loading import load_structured_patch_json_with_deterministic_repairs
from harnesses.structured_patch.patch_parse_contract import canonical_structured_patch_op_name
from core.schemas import StructuredOutputError


def structured_patch_payload_is_noop(payload: Any) -> bool:
    if payload is None:
        return True
    if isinstance(payload, list):
        return not payload or all(structured_patch_payload_is_noop(item) for item in payload)
    if not isinstance(payload, dict):
        return False
    if isinstance(payload.get("operations"), list):
        return structured_patch_payload_is_noop(payload["operations"])
    if isinstance(payload.get("ops"), list):
        return structured_patch_payload_is_noop(payload["ops"])
    op_name = canonical_structured_patch_op_name(payload.get("op") or payload.get("operation") or payload.get("type"))
    return op_name == "noop"


def structured_patch_output_is_noop(raw_output: str) -> bool:
    stripped = raw_output.strip()
    if not stripped:
        return True

    unfenced = stripped
    fence_match = re.fullmatch(r"```(?:jsonl?|JSONL?)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    if fence_match:
        unfenced = fence_match.group(1).strip()
        if not unfenced:
            return True

    if re.fullmatch(r"(?i)(?:no[_\s-]?op|noop)", unfenced):
        return True

    if "{" not in unfenced and "[" not in unfenced:
        normalized = re.sub(r"\s+", " ", unfenced).strip().rstrip(".").lower()
        explicit_noop_texts = {
            "an empty patch is emitted as no corrections are required",
            "no corrections are required",
            "no corrections required",
            "no operations are required",
            "no operations required",
            "no patch operations are required",
            "no patch operations required",
            "no changes are required",
            "no changes required",
        }
        return normalized in explicit_noop_texts

    try:
        payload = load_structured_patch_json_with_deterministic_repairs(unfenced)[0]
    except (json.JSONDecodeError, ValueError, StructuredOutputError):
        return False
    return structured_patch_payload_is_noop(payload)


__all__ = [
    "structured_patch_output_is_noop",
    "structured_patch_payload_is_noop",
]
