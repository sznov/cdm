from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from backend.persistence.result_records import update_result_record, write_result_record
from backend.persistence.run_path_references import normalize_web_run_path_references
from backend.services.run_stream_records import (
    RunStreamRecordContext,
    update_run_stream_record,
)
from core.config_safety import redact_persisted_value
from harnesses.structured_patch.decision_identifier_context import propose_identifier_context_decision_patches
from harnesses.structured_patch.decision_merge import merge_decision_patches
from backend.services.decision_patches import decision_patches_from_result_payload, persist_decision_patches
from backend.services.recorded_patch_policy import recorded_patch_policy


@dataclass(frozen=True, slots=True)
class PersistedRunResult:
    result_payload: dict[str, Any] | None
    correction_sequence: dict[str, Any] | None


def persist_primary_run_result(record_context: RunStreamRecordContext, result: Any) -> dict[str, Any]:
    patch_policy = recorded_patch_policy(record_context.run_record)
    result_payload = redact_persisted_value(
        normalize_web_run_path_references(
            result.to_dict(),
            run_dir=record_context.run_dir,
        )
    )
    if not isinstance(result_payload, dict):  # pragma: no cover - result object contract
        raise TypeError("Result redaction must preserve its object shape.")
    result_payload = write_result_record(record_context.run_dir, result_payload)
    decision_patches = decision_patches_from_result_payload(
        result_payload,
        name_policy=patch_policy.name_policy,
    )
    if record_context.effective_harness_run_spec.effective_config.infer_implicit_identifiers:
        decision_patches = merge_decision_patches(
            decision_patches,
            propose_identifier_context_decision_patches(
                result.structured_model,
                name_policy=patch_policy.name_policy,
            ),
            name_policy=patch_policy.name_policy,
        )
    if decision_patches:
        persist_decision_patches(
            record_context.run_dir,
            decision_patches,
            name_policy=patch_policy.name_policy,
        )
    return result_payload


def persist_run_result_transaction(
    record_context: RunStreamRecordContext,
    *,
    result: Any | None,
    correction_sequence: dict[str, Any] | None,
) -> PersistedRunResult:
    """Publish one worker result and its correction metadata in fixed order."""

    result_payload = (
        persist_primary_run_result(record_context, result)
        if result is not None
        else None
    )
    detached_correction = redact_persisted_value(
        normalize_web_run_path_references(
            deepcopy(correction_sequence),
            run_dir=record_context.run_dir,
        )
    )
    if detached_correction is not None and not isinstance(detached_correction, dict):
        raise TypeError("Correction-sequence redaction must preserve object shape.")
    if result_payload is not None and detached_correction is not None:
        result_payload = update_result_record(
            record_context.run_dir,
            correction_sequence=detached_correction,
        )
    if detached_correction is not None:
        update_run_stream_record(
            record_context,
            correction_sequence=detached_correction,
        )
    return PersistedRunResult(
        result_payload=result_payload,
        correction_sequence=detached_correction,
    )


__all__ = [
    "PersistedRunResult",
    "persist_primary_run_result",
    "persist_run_result_transaction",
]
