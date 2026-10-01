from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from core.json_parsing import (
    extract_json_object,
    format_validation_error,
    iter_balanced_json_objects,
    reject_duplicate_json_keys,
    strip_model_thought_blocks,
)
from core.json_repair_loading import load_structured_json_with_deterministic_repairs
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
    StructuredNamePolicyError,
)
from harnesses.structured_patch.model_issue_parsing import parse_structured_model_issues_payload
from harnesses.structured_patch.model_malformed_json_repair import (
    repair_extra_trailing_object_closes,
    repair_malformed_structured_json,
    repair_missing_entities_array_close,
    repair_missing_json_closers,
    repair_missing_relationship_object_closes,
)
from harnesses.structured_patch.model_repair import repair_structured_model_payload
from core.schemas import StructuredModel, StructuredOutputError, validate_structured_model_links

def extract_structured_model_json_object(raw_output: str) -> str:
    thought_stripped = strip_model_thought_blocks(raw_output)
    fallback = extract_json_object(thought_stripped)
    for source in (thought_stripped, raw_output):
        for candidate in iter_balanced_json_objects(source):
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get("entities"), list) and isinstance(payload.get("relationships"), list):
                return candidate
    return fallback


def parse_structured_model_raw_payload_with_repairs(raw_output: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    extracted = extract_structured_model_json_object(raw_output)
    repairs: list[dict[str, Any]] = []
    try:
        payload = json.loads(extracted, object_pairs_hook=reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        repaired = repair_malformed_structured_json(extracted)
        if repaired != extracted:
            try:
                payload, repairs = load_structured_json_with_deterministic_repairs(repaired)
            except json.JSONDecodeError:
                raise StructuredOutputError(f"Structured JSON parsing failed. {exc.msg} at line {exc.lineno} column {exc.colno}.") from exc
            except ValueError as repair_exc:
                raise StructuredOutputError(f"Structured JSON parsing failed. {repair_exc}") from repair_exc
        else:
            raise StructuredOutputError(f"Structured JSON parsing failed. {exc.msg} at line {exc.lineno} column {exc.colno}.") from exc
    except ValueError as exc:
        try:
            payload, repairs = load_structured_json_with_deterministic_repairs(extracted)
        except (json.JSONDecodeError, ValueError) as repair_exc:
            raise StructuredOutputError(f"Structured JSON parsing failed. {repair_exc}") from repair_exc
    if not isinstance(payload, dict):
        raise StructuredOutputError("Structured JSON output must be an object.")
    return payload, repairs


def parse_structured_model_raw_payload(raw_output: str) -> dict[str, Any]:
    payload, _repairs = parse_structured_model_raw_payload_with_repairs(raw_output)
    return payload


def parse_structured_model_packet_output_with_repairs(
    raw_output: str,
    *,
    repair_missing_endpoint_entities: bool = False,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> tuple[StructuredModel, list[dict[str, Any]], list[dict[str, Any]]]:
    raw_payload, deterministic_repairs = parse_structured_model_raw_payload_with_repairs(raw_output)
    issues = parse_structured_model_issues_payload(raw_payload.get("issues"))
    if deterministic_repairs:
        for index, repair in enumerate(deterministic_repairs, start=1):
            repair.setdefault("id", f"JR{index}")
        issues = parse_structured_model_issues_payload(deterministic_repairs) + issues
    try:
        payload = repair_structured_model_payload(
            raw_payload,
            repair_missing_endpoint_entities=repair_missing_endpoint_entities,
            name_policy=name_policy,
        )
        model = StructuredModel.model_validate(payload)
        name_policy.validate_model_names(model)
    except StructuredNamePolicyError as exc:
        raise StructuredOutputError(f"Structured name validation failed. {exc}") from exc
    except ValidationError as exc:
        raise StructuredOutputError(f"Structured JSON schema validation failed. {format_validation_error(exc)}") from exc

    validate_structured_model_links(model)
    return model, issues, deterministic_repairs


def parse_structured_model_packet_output(
    raw_output: str,
    *,
    repair_missing_endpoint_entities: bool = False,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> tuple[StructuredModel, list[dict[str, Any]]]:
    model, issues, _repairs = parse_structured_model_packet_output_with_repairs(
        raw_output,
        repair_missing_endpoint_entities=repair_missing_endpoint_entities,
        name_policy=name_policy,
    )
    return model, issues


def parse_structured_model_output(
    raw_output: str,
    *,
    repair_missing_endpoint_entities: bool = False,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> StructuredModel:
    model, _issues = parse_structured_model_packet_output(
        raw_output,
        repair_missing_endpoint_entities=repair_missing_endpoint_entities,
        name_policy=name_policy,
    )
    return model

__all__ = [
    "extract_structured_model_json_object",
    "parse_structured_model_output",
    "parse_structured_model_packet_output",
    "parse_structured_model_packet_output_with_repairs",
    "parse_structured_model_raw_payload",
    "parse_structured_model_raw_payload_with_repairs",
    "repair_extra_trailing_object_closes",
    "repair_malformed_structured_json",
    "repair_missing_entities_array_close",
    "repair_missing_json_closers",
    "repair_missing_relationship_object_closes",
]
