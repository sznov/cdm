from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.model_call_logger import ModelCallLogger
from core.operation_loop_result import OperationLoopResult
from core.plantuml_structured import render_structured_model_to_plantuml
from core.schemas import StructuredModel
from harnesses.structured_patch.model_conversion import structured_model_to_working_model
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.decision_merge import merge_decision_patches_latest_state
from harnesses.structured_patch.patch_application_deferred import operation_payload_signature
from harnesses.structured_patch.patch_application_records import (
    accepted_operation_history_record,
    deferred_operation_history_record,
    rejected_operation_history_record,
)
from harnesses.structured_patch.result_building import structured_patch_rejected_count
from harnesses.structured_patch.required_correction_types import (
    CorrectionPhaseState,
    StepOutcomeBaseline,
    StepOutcomeSummary,
)


@dataclass(frozen=True, slots=True)
class ReconciledHistory:
    records: list[dict[str, Any]]
    added_count: int


def model_call_log_counter(model_call_log_dir: Path | None) -> int:
    if model_call_log_dir is None or not model_call_log_dir.is_dir():
        return 0
    return len(list(model_call_log_dir.glob("*.txt")))


def decision_patches_from_result(
    result: OperationLoopResult,
    *,
    canonicalize_latest_state: bool,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    for check in result.completion_checks:
        if isinstance(check, dict) and isinstance(check.get("decision_patches"), list):
            patches.extend(deepcopy(item) for item in check["decision_patches"] if isinstance(item, dict))
    if canonicalize_latest_state:
        return merge_decision_patches_latest_state(
            patches,
            name_policy=name_policy,
        )
    return patches


def initialize_phase_state(
    result: OperationLoopResult,
    *,
    canonicalize_latest_decision_state: bool,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> CorrectionPhaseState:
    decision_patches = decision_patches_from_result(
        result,
        canonicalize_latest_state=canonicalize_latest_decision_state,
        name_policy=name_policy,
    )
    return CorrectionPhaseState(
        structured_model=result.structured_model.model_copy(deep=True),
        operation_history=deepcopy(result.operation_history),
        input_prompts=deepcopy(result.input_prompts),
        usage_steps=deepcopy(result.usage_steps),
        decision_patches=decision_patches,
        base_decision_patches=deepcopy(decision_patches),
        completion_model=result.model,
    )


def capture_step_baseline(
    state: CorrectionPhaseState,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> StepOutcomeBaseline:
    return StepOutcomeBaseline(
        applied=len(state.applied_operations),
        satisfied=len(state.already_satisfied_operations),
        rejected=len(state.rejected_operations),
        deferred=len(state.deferred_operations),
        history=len(state.operation_history),
        deferred_signatures=frozenset(
            operation_payload_signature(item.get("op"), name_policy=name_policy)
            for item in state.deferred_operations
        ),
    )


def _recorded_result_ids(operation_history: list[dict[str, Any]]) -> set[int]:
    return {
        id(entry["result"])
        for history_item in operation_history
        for field in ("accepted", "rejected", "deferred")
        for entry in history_item.get(field) or []
        if isinstance(entry, dict) and isinstance(entry.get("result"), dict)
    }


def _recorded_deferred_signatures(
    operation_history: list[dict[str, Any]],
    *,
    name_policy: StructuredNamePolicy,
) -> set[str]:
    return {
        operation_payload_signature(entry.get("op"), name_policy=name_policy)
        for history_item in operation_history
        for entry in history_item.get("deferred") or []
        if isinstance(entry, dict)
    }


def reconciled_operation_history(
    *,
    operation_history: list[dict[str, Any]],
    applied_operations: list[dict[str, Any]],
    already_satisfied_operations: list[dict[str, Any]],
    rejected_operations: list[dict[str, Any]],
    deferred_operations: list[dict[str, Any]],
    iteration: int,
    default_sequence: int,
    normalize_from: int,
    include_deferred: bool,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> ReconciledHistory:
    """Return exact-once outcome provenance without mutating phase inputs."""

    records = list(operation_history)
    recorded_result_ids = _recorded_result_ids(records)
    added_count = 0
    for result in (*applied_operations, *already_satisfied_operations):
        if id(result) in recorded_result_ids:
            continue
        records.append(
            accepted_operation_history_record(
                int(result.get("sequence") or default_sequence),
                result,
            )
        )
        recorded_result_ids.add(id(result))
        added_count += 1
    for result in rejected_operations:
        if id(result) in recorded_result_ids:
            continue
        records.append(
            rejected_operation_history_record(
                int(result.get("sequence") or default_sequence),
                result.get("op"),
                result.get("reason"),
                result,
            )
        )
        recorded_result_ids.add(id(result))
        added_count += 1
    if include_deferred:
        recorded_signatures = _recorded_deferred_signatures(
            records,
            name_policy=name_policy,
        )
        for result in deferred_operations:
            signature = operation_payload_signature(
                result.get("op"),
                name_policy=name_policy,
            )
            if signature in recorded_signatures:
                continue
            records.append(
                deferred_operation_history_record(
                    int(
                        result.get("last_retry_sequence")
                        or result.get("sequence")
                        or default_sequence
                    ),
                    result,
                )
            )
            recorded_signatures.add(signature)
            added_count += 1
    normalized = [
        record if index < normalize_from else {**record, "iteration": iteration}
        for index, record in enumerate(records)
    ]
    return ReconciledHistory(records=normalized, added_count=added_count)


def step_outcome_summary(
    state: CorrectionPhaseState,
    baseline: StepOutcomeBaseline,
    *,
    unified_sequence: bool,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> StepOutcomeSummary:
    deferred_after = {
        operation_payload_signature(item.get("op"), name_policy=name_policy)
        for item in state.deferred_operations
    }
    return StepOutcomeSummary(
        accepted_count=(
            len(state.applied_operations) - baseline.applied
            + len(state.already_satisfied_operations) - baseline.satisfied
        ),
        changed_count=len(state.applied_operations) - baseline.applied,
        rejected_count=len(state.rejected_operations) - baseline.rejected,
        deferred_count=(
            len(deferred_after - set(baseline.deferred_signatures))
            if unified_sequence
            else len(state.deferred_operations) - baseline.deferred
        ),
        resolved_deferred_count=len(set(baseline.deferred_signatures) - deferred_after),
        remaining_deferred_count=len(deferred_after),
    )


def build_correction_result(
    *,
    base_result: OperationLoopResult,
    state: CorrectionPhaseState,
    completion_record: dict[str, Any],
    logger: ModelCallLogger,
    phase_count: int,
    stop_reason: str,
) -> OperationLoopResult:
    working_model = structured_model_to_working_model(state.structured_model)
    plantuml = render_structured_model_to_plantuml(state.structured_model)
    return OperationLoopResult(
        job_id=base_result.job_id,
        working_model=working_model,
        structured_model=state.structured_model,
        plantuml=plantuml,
        plantuml_url="",
        operation_history=deepcopy(state.operation_history),
        input_prompts=deepcopy(state.input_prompts),
        completion_checks=[*deepcopy(base_result.completion_checks), deepcopy(completion_record)],
        plan_updates=deepcopy(base_result.plan_updates),
        model_call_log_dir=base_result.model_call_log_dir,
        model_call_logs=[*deepcopy(base_result.model_call_logs), *deepcopy(logger.records)],
        iterations=base_result.iterations + max(1, phase_count) + int(state.language_repair_ran),
        accepted_operation_count=base_result.accepted_operation_count + len(state.applied_operations),
        rejected_operation_count=correction_phase_rejected_count(
            base_result=base_result,
            state=state,
        ),
        stop_reason=stop_reason,
        model=state.completion_model,
        usage_steps=deepcopy(state.usage_steps),
    )


def correction_phase_rejected_count(
    *,
    base_result: OperationLoopResult,
    state: CorrectionPhaseState,
) -> int:
    """Count correction rejections once, including non-patch phase failures."""

    correction_history = state.operation_history[len(base_result.operation_history) :]
    return base_result.rejected_operation_count + structured_patch_rejected_count(
        operation_history=correction_history,
        rejected_operations=state.rejected_operations,
    )


def build_done_payload(
    *,
    job_id: str,
    template_id: str,
    template_name: str,
    policy_id: str,
    state: CorrectionPhaseState,
    refined: bool,
    checkpoint_stage: str,
) -> dict[str, Any]:
    accepted_count = len(state.applied_operations) + len(state.already_satisfied_operations)
    payload: dict[str, Any] = {
        "job_id": job_id,
        "template_id": template_id,
        "template_name": template_name,
        "phase_results": deepcopy(state.phase_results),
        "accepted_count": accepted_count,
        "changed_count": len(state.applied_operations),
        "rejected_count": len(state.rejected_operations),
        "deferred_count": len(state.deferred_operations),
        "checkpoint_stage": checkpoint_stage,
        "summary": (
            f"Correction sequence complete: {accepted_count} accepted/already satisfied, "
            f"{len(state.applied_operations)} changed, {len(state.rejected_operations)} rejected, "
            f"{len(state.deferred_operations)} deferred."
        ),
    }
    if refined:
        payload.update(
            {
                "policy_id": policy_id,
                "language_repair": deepcopy(state.language_repair_record),
                "pre_correction_checkpoint": deepcopy(state.pre_correction_checkpoint),
                "decision_patches": deepcopy(state.decision_patches),
                "deferred_operations": deepcopy(state.deferred_operations),
            }
        )
    return payload


__all__ = [
    "ReconciledHistory",
    "build_correction_result",
    "build_done_payload",
    "capture_step_baseline",
    "correction_phase_rejected_count",
    "decision_patches_from_result",
    "initialize_phase_state",
    "model_call_log_counter",
    "reconciled_operation_history",
    "step_outcome_summary",
]
