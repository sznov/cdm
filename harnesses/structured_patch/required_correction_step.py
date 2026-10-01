from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from core.model_call_completion import complete_with_logging
from core.model_call_logger import ModelCallLogger
from core.model_client import ChatMessage, TextModelClient
from harnesses.structured_patch.correction_policy import CorrectionPhasePolicy
from harnesses.structured_patch.required_correction_events import (
    CorrectionApplicationEventEmitter,
    CorrectionSnapshotEmitter,
    CorrectionTokenEmitter,
    emit_new_model_call_logs,
)
from harnesses.structured_patch.required_correction_provenance import (
    capture_step_baseline,
    reconciled_operation_history,
    step_outcome_summary,
)
from harnesses.structured_patch.required_correction_types import (
    CorrectionExecutionError,
    CorrectionPhaseState,
    CorrectionStepInput,
    CorrectionTemplateIdentity,
    StepOutcomeBaseline,
)
from harnesses.structured_patch.patch_application_phase import (
    StructuredPatchApplicationCallbacks,
    StructuredPatchApplicationPolicy,
    StructuredPatchApplicationState,
    StructuredPatchBatchApplier,
)
from harnesses.structured_patch.patch_application_records import (
    operation_applied_payload,
    operation_candidate_payload,
    rejected_operation_history_record,
    rejected_operation_result,
)
from harnesses.structured_patch.patch_parse_contract import canonical_structured_patch_op_name
from harnesses.structured_patch.patch_parse_stream import parse_structured_patch_operations
from harnesses.structured_patch.patch_prompts import (
    build_patch_operation_clerk_user_prompt,
)
from harnesses.structured_patch.runner_prompt_profile import async_op_patch_prompt_profile
from harnesses.structured_patch.run_events import StructuredPatchRunEvents


_PROMPT_DECISION_FIELDS = (
    "id",
    "status",
    "kind",
    "title",
    "question",
    "reason",
    "evidence",
    "operation",
    "source",
    "signature",
    "target",
    "options",
    "blocked_by",
    "overlap_kind",
)
_CONVERSATION_CONTEXT_FIELDS = {
    "chat",
    "comment",
    "comments",
    "decision_comments",
    "messages",
    "session_chat",
    "user_comment",
}


def correction_step_input(raw_step: dict[str, Any], *, index: int, count: int) -> CorrectionStepInput:
    message = str(raw_step.get("message") or "").strip()
    return CorrectionStepInput(
        index=index,
        count=count,
        step_id=str(raw_step.get("id") or f"step-{index}"),
        name=str(raw_step.get("name") or f"Step {index}"),
        summary_label=str(raw_step.get("name") or message),
        message=message,
        allowed_ops=frozenset(
            str(op).strip()
            for op in (raw_step.get("allowed_ops") or [])
            if str(op).strip()
        ),
    )


def _without_conversation_context(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_conversation_context(item)
            for key, item in value.items()
            if str(key).lower() not in _CONVERSATION_CONTEXT_FIELDS
        }
    if isinstance(value, list):
        return [_without_conversation_context(item) for item in value]
    return deepcopy(value)


def _prompt_decision_patches(
    decision_patches: list[dict[str, Any]],
    *,
    exclude_conversation_context: bool,
) -> list[dict[str, Any]]:
    if not exclude_conversation_context:
        return deepcopy(decision_patches)
    return [
        _without_conversation_context(
            {key: patch[key] for key in _PROMPT_DECISION_FIELDS if key in patch}
        )
        for patch in decision_patches
    ]


def _correction_findings_json(message: str) -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "kind": "posthoc_correction",
                    "target": "current model",
                    "summary": message,
                    "evidence": "",
                }
            ]
        },
        ensure_ascii=False,
        indent=2,
    )


def _build_user_prompt(
    *,
    specification: str,
    step: CorrectionStepInput,
    state: CorrectionPhaseState,
    policy: CorrectionPhasePolicy,
    max_operations: int | None,
) -> str:
    prompt_profile = async_op_patch_prompt_profile(
        direct_microop_judge=False,
        name_policy=policy.name_policy,
    )
    prompt = build_patch_operation_clerk_user_prompt(
        specification=specification,
        coverage_findings_json=_correction_findings_json(step.message),
        structured_model_json=json.dumps(
            state.structured_model.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        ),
        pending_decisions_json=json.dumps(
            {
                "decision_patches": _prompt_decision_patches(
                    state.decision_patches,
                    exclude_conversation_context=policy.refined,
                )
            },
            ensure_ascii=False,
            indent=2,
        ),
        template=prompt_profile.correction_patch_user_template,
    )
    prompt += (
        "\nEmit all operations needed for the requested correction.\n"
        if max_operations is None
        else f"\nStop after at most {max_operations} operations.\n"
    )
    if step.allowed_ops:
        prompt += (
            "\nFor this correction request, allowed operation op values are: "
            f"{', '.join(sorted(step.allowed_ops))}. If the check finds no issue, or if a correct fix would require "
            'any other operation type, emit exactly {"op":"noop"}.\n'
        )
    return prompt


async def _reject_legacy_disallowed_operation(
    *,
    sequence: int,
    operation: dict[str, Any],
    allowed_ops: frozenset[str],
    state: CorrectionPhaseState,
    events: StructuredPatchRunEvents,
) -> None:
    operation_name = canonical_structured_patch_op_name(
        operation.get("op") or operation.get("operation") or operation.get("type")
    )
    reason = (
        f"Operation type '{operation_name or '<missing>'}' is not allowed for this correction step. "
        f"Allowed operation types: {', '.join(sorted(allowed_ops))}."
    )
    await events.emit("structured_patch_operation_candidate", operation_candidate_payload(sequence, operation))
    result = rejected_operation_result(sequence, operation, reason)
    state.rejected_operations.append(result)
    state.operation_history.append(rejected_operation_history_record(sequence, operation, reason, result))
    await events.emit(
        "structured_patch_operation_applied",
        operation_applied_payload(status="rejected", result=result, summary=reason),
    )


def _sync_application_state(
    *,
    state: CorrectionPhaseState,
    applier: StructuredPatchBatchApplier,
    baseline: StepOutcomeBaseline,
    base_iterations: int,
    policy: CorrectionPhasePolicy,
    include_deferred: bool,
) -> None:
    state.structured_model = applier.model
    state.decision_patches = applier.decision_patches
    if not policy.refined:
        return
    state.deferred_retry_fingerprint = applier.last_deferred_retry_fingerprint
    state.operation_sequence = applier.operation_count()
    reconciliation = reconciled_operation_history(
        operation_history=state.operation_history,
        applied_operations=state.applied_operations,
        already_satisfied_operations=state.already_satisfied_operations,
        rejected_operations=state.rejected_operations,
        deferred_operations=state.deferred_operations,
        iteration=base_iterations + len(state.phase_results) + 1,
        default_sequence=state.operation_sequence,
        normalize_from=baseline.history,
        include_deferred=include_deferred,
        name_policy=policy.name_policy,
    )
    state.operation_history[:] = reconciliation.records


async def _apply_operations(
    *,
    operations: list[dict[str, Any]],
    step: CorrectionStepInput,
    specification: str,
    state: CorrectionPhaseState,
    policy: CorrectionPhasePolicy,
    events: StructuredPatchRunEvents,
    baseline: StepOutcomeBaseline,
    base_iterations: int,
    applier_type: type[StructuredPatchBatchApplier],
) -> None:
    applier = applier_type(
        specification=specification,
        state=StructuredPatchApplicationState(
            model=state.structured_model,
            decision_patches=state.decision_patches,
            applied_operations=state.applied_operations,
            rejected_operations=state.rejected_operations,
            already_satisfied_operations=state.already_satisfied_operations,
            deferred_operations=state.deferred_operations,
            operation_history=state.operation_history,
        ),
        callbacks=StructuredPatchApplicationCallbacks(
            emit=CorrectionApplicationEventEmitter(events, policy.refined),
            emit_partial_snapshot=CorrectionSnapshotEmitter(events, state, policy.refined),
        ),
        policy=StructuredPatchApplicationPolicy(
            operation_guard=policy.operation_guard,
            validate_deferred_retries=policy.refined,
            preserve_provisional_identifier=policy.refined,
            allowed_ops=step.allowed_ops if policy.refined else frozenset(),
            initial_sequence=state.operation_sequence if policy.refined else 0,
            last_deferred_retry_fingerprint=(
                state.deferred_retry_fingerprint if policy.refined else None
            ),
            name_policy=policy.name_policy,
        ),
    )
    legacy_disallowed_sequence = 0
    try:
        for operation in operations:
            operation_name = canonical_structured_patch_op_name(
                operation.get("op") or operation.get("operation") or operation.get("type")
            )
            if not policy.refined and step.allowed_ops and operation_name not in step.allowed_ops:
                legacy_disallowed_sequence += 1
                await _reject_legacy_disallowed_operation(
                    sequence=legacy_disallowed_sequence,
                    operation=operation,
                    allowed_ops=step.allowed_ops,
                    state=state,
                    events=events,
                )
                continue
            await applier.apply_parsed_operation(operation)
        await applier.retry_deferred_operations()
        await applier.apply_queued_relationship_removals()
        await applier.retry_deferred_operations()
        await applier.apply_queued_attribute_removals()
        await applier.retry_deferred_operations()
    except Exception as exc:
        _sync_application_state(
            state=state,
            applier=applier,
            baseline=baseline,
            base_iterations=base_iterations,
            policy=policy,
            include_deferred=policy.refined,
        )
        raise CorrectionExecutionError("posthoc_correction_application", exc) from exc
    _sync_application_state(
        state=state,
        applier=applier,
        baseline=baseline,
        base_iterations=base_iterations,
        policy=policy,
        include_deferred=False,
    )


async def execute_correction_step(
    *,
    step: CorrectionStepInput,
    template: CorrectionTemplateIdentity,
    specification: str,
    state: CorrectionPhaseState,
    base_iterations: int,
    client: TextModelClient,
    logger: ModelCallLogger,
    events: StructuredPatchRunEvents,
    policy: CorrectionPhasePolicy,
    max_operations: int | None,
    transport_retries: int | None,
    applier_type: type[StructuredPatchBatchApplier],
) -> dict[str, Any]:
    step_payload = step.event_payload(job_id=events.job_id, template=template)
    await events.emit("correction_sequence_step_start", step_payload)
    user_prompt = _build_user_prompt(
        specification=specification,
        step=step,
        state=state,
        policy=policy,
        max_operations=max_operations,
    )
    messages: list[ChatMessage] = [{"role": "user", "content": user_prompt}]
    prompt_profile = async_op_patch_prompt_profile(
        direct_microop_judge=False,
        name_policy=policy.name_policy,
    )
    prompt_payload = {
        "agent_id": "patchOperationClerk",
        "title": "Post-hoc correction patch prompt",
        "summary": "Post-hoc correction step resolved against the current structured model.",
        "system_prompt": prompt_profile.correction_patch_system_prompt,
        "messages": messages,
    }
    state.input_prompts.append(prompt_payload)
    await events.emit("input_prompt", prompt_payload)
    await events.emit(
        "correction_patch_generation_start",
        {
            "job_id": events.job_id,
            "agent_id": "patchOperationClerk",
            "summary": "Streaming post-hoc correction patch model output.",
        },
    )
    metadata: dict[str, Any] = {
        "harness": "structured-patch-posthoc",
        "stage": "posthoc_correction",
        "step_id": step.step_id,
        "max_operations": max_operations,
        "allowed_ops": sorted(step.allowed_ops) if step.allowed_ops else None,
    }
    if policy.refined:
        metadata["policy_id"] = policy.policy_id
    try:
        completion, log_record = await complete_with_logging(
            client=client,
            logger=logger,
            kind="posthoc_correction_patch_operation",
            system_prompt=prompt_profile.correction_patch_system_prompt,
            user_content=user_prompt,
            messages=messages,
            on_token=CorrectionTokenEmitter(events, events.job_id),
            transport_retries=transport_retries,
            metadata=metadata,
        )
    except Exception as exc:
        raise CorrectionExecutionError("posthoc_correction", exc) from exc
    state.completion_model = completion.model or state.completion_model
    state.usage_steps.append(completion.usage)
    if policy.refined:
        await emit_new_model_call_logs(events=events, logger=logger, state=state)
    elif log_record is not None:
        await events.emit("model_call_log", log_record)
        state.emitted_log_count = len(logger.records)
    await events.emit(
        "correction_patch_generation_done",
        {
            "job_id": events.job_id,
            "agent_id": "patchOperationClerk",
            "raw_output": completion.text,
            "summary": "Post-hoc correction patch model call completed.",
        },
    )
    parse_error: str | None = None
    try:
        operations = parse_structured_patch_operations(completion.text)
        if max_operations is not None:
            operations = operations[:max_operations]
    except Exception as exc:
        operations = []
        parse_error = str(exc)
        await events.emit(
            "structured_patch_operation_parse_error",
            {
                "job_id": events.job_id,
                "agent_id": "patchOperationClerk",
                "error": parse_error,
                "raw_output": completion.text,
                "summary": "Could not parse structured patch operations from post-hoc correction output.",
            },
        )
    baseline = capture_step_baseline(state, name_policy=policy.name_policy)
    await _apply_operations(
        operations=operations,
        step=step,
        specification=specification,
        state=state,
        policy=policy,
        events=events,
        baseline=baseline,
        base_iterations=base_iterations,
        applier_type=applier_type,
    )
    summary = step_outcome_summary(
        state,
        baseline,
        unified_sequence=policy.refined,
        name_policy=policy.name_policy,
    )
    phase = {
        **step_payload,
        "accepted_count": summary.accepted_count,
        "changed_count": summary.changed_count,
        "rejected_count": summary.rejected_count,
        "deferred_count": summary.deferred_count,
        "parse_error": parse_error,
    }
    if policy.refined:
        phase["resolved_deferred_count"] = summary.resolved_deferred_count
        phase["remaining_deferred_count"] = summary.remaining_deferred_count
    state.phase_results.append(phase)
    if parse_error and policy.refined:
        await events.emit(
            "correction_sequence_step_failed",
            {
                **phase,
                "status": "failed",
                "error": parse_error,
                "summary": f"Correction sequence step {step.index}/{step.count} failed: {parse_error}",
            },
        )
        raise CorrectionExecutionError(
            "posthoc_correction_parse",
            parse_error,
            phase_already_recorded=True,
        )
    await events.emit(
        "correction_sequence_step_done",
        {
            **phase,
            "summary": (
                f"Correction sequence step {step.index}/{step.count} complete: "
                f"{summary.accepted_count} accepted/already satisfied, "
                f"{summary.changed_count} changed, {summary.rejected_count} rejected."
            ),
        },
    )
    return phase


__all__ = ["correction_step_input", "execute_correction_step"]
