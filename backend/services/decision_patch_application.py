from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.api.models import DecisionPatchApplyRequest
from backend.persistence.common import utc_now_iso
from backend.services.active_run_registry import ActiveRun, run_is_active
from backend.services.decision_patch_application_context import (
    emit_decision_patch_batch_start,
    load_decision_patch_application_context,
    validate_decision_choices,
)
from backend.services.decision_patch_application_persistence import (
    commit_decision_patch_application,
)
from harnesses.structured_patch.patch_operation_apply import apply_structured_patch_operation
from backend.services.decision_patches import (
    decision_option_by_id,
    decision_option_operation,
    merge_identifier_context_operation,
    rebase_decision_operation_for_current_model,
    update_decision_patch_operation_references,
)
from backend.services.run_operation_claims import claim_recorded_run_operation
from backend.services.run_operation_registry import (
    RunOperationHandle,
    RunOperationKind,
    RunOperationRegistry,
)
from backend.services.async_file_work import run_thread_to_completion


def decision_choices_from_request(request: DecisionPatchApplyRequest) -> list[dict[str, Any]]:
    if request.decisions:
        choices: list[dict[str, Any]] = []
        for decision in request.decisions:
            patch_id = decision.patch_id.strip()
            if not patch_id:
                continue
            choices.append(
                {
                    "patch_id": patch_id,
                    "option_id": str(decision.option_id or "apply").strip() or "apply",
                    "label": str(decision.label or "").strip(),
                    "custom_text": str(decision.custom_text or "").strip(),
                }
            )
        return choices
    return [
        {"patch_id": str(patch_id).strip(), "option_id": "apply", "label": "", "custom_text": ""}
        for patch_id in request.patch_ids
        if str(patch_id).strip()
    ]


def _apply_decision_patches_transaction(
    job_id: str,
    request: DecisionPatchApplyRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_id: str,
) -> dict[str, Any]:
    context = load_decision_patch_application_context(
        job_id,
        runs_dir=runs_dir,
        sessions_dir=sessions_dir,
        active_runs=active_runs,
    )
    if not hasattr(context, "event_sequences"):
        context.event_sequences = []
    model = context.model
    choices = decision_choices_from_request(request)
    requested_ids = validate_decision_choices(
        choices,
        context.patch_by_id,
        name_policy=context.patch_policy.name_policy,
    )
    emit_decision_patch_batch_start(context, requested_ids=requested_ids, choices=choices)

    results: list[dict[str, Any]] = []
    applied_events: list[dict[str, Any]] = []
    chat_selections: list[dict[str, Any]] = []
    accepted_count = 0
    noted_count = 0
    rejected_count = 0
    changed_count = 0
    for choice in choices:
        patch_id = choice["patch_id"]
        patch = context.patch_by_id[patch_id]
        option = decision_option_by_id(
            patch,
            choice.get("option_id"),
            name_policy=context.patch_policy.name_policy,
        )
        operation = decision_option_operation(option)
        option_id = str(option.get("id") or choice.get("option_id") or "apply").strip() or "apply"
        label = choice.get("label") or str(option.get("label") or patch.get("title") or patch_id).strip()
        custom_text = str(choice.get("custom_text") or "").strip()
        if option.get("requires_text") and not custom_text:
            raise HTTPException(status_code=400, detail=f"Decision option requires text: {patch_id}.{option_id}")

        if not isinstance(operation, dict):
            result = {
                "status": "noted",
                "reason": custom_text or f"Decision recorded: {label}",
                "op": None,
            }
            noted_count += 1
        else:
            operation_to_apply = rebase_decision_operation_for_current_model(
                operation,
                model,
                context.decision_rename_maps,
                name_policy=context.patch_policy.name_policy,
            )
            operation_to_apply, merged_identifier_context = merge_identifier_context_operation(
                operation_to_apply,
                model,
                patch,
                name_policy=context.patch_policy.name_policy,
            )
            # A decision patch is an explicit user selection. Guarded-v1 has
            # historically applied those choices without the automatic
            # correction veto; only name interpretation follows the recorded
            # protocol here.
            after, result = apply_structured_patch_operation(
                model,
                operation_to_apply,
                name_policy=context.patch_policy.name_policy,
            )
            if operation_to_apply != operation:
                if merged_identifier_context:
                    result["merged_from"] = operation
                    result["merge_reason"] = "Identifier-context decision was merged with existing identifier relationship parts."
                else:
                    result["rebased_from"] = operation
                    result["rebase_reason"] = "Decision operation references were rebased through accepted model renames."
                    update_decision_patch_operation_references(patch, option_id, operation, operation_to_apply)
                    if option.get("operation") == operation:
                        option["operation"] = operation_to_apply
            if result.get("status") == "accepted":
                model = after
                accepted_count += 1
                changed_count += 1
            elif result.get("status") == "already_satisfied":
                accepted_count += 1
            else:
                rejected_count += 1
        result_payload = {
            "patch_id": patch_id,
            "option_id": option_id,
            "option": option,
            "label": label,
            "custom_text": custom_text,
            "patch": patch,
            "result": result,
        }
        results.append(result_payload)
        if result.get("status") in {"accepted", "already_satisfied"}:
            patch["status"] = "applied"
            patch["applied_at_utc"] = utc_now_iso()
        elif result.get("status") == "noted":
            patch["status"] = "noted"
            patch["noted_at_utc"] = utc_now_iso()
        else:
            patch["status"] = "rejected"
            patch["rejected_at_utc"] = utc_now_iso()
        patch["selected_option_id"] = option_id
        patch["selected_option_label"] = label
        if custom_text:
            patch["selected_option_text"] = custom_text
        patch["applied_result"] = result
        chat_selections.append({"patch": patch, "label": label, "custom_text": custom_text})
        applied_events.append(
            {
                "agent_id": "incrementalOpApplier",
                "patch_id": patch_id,
                "option_id": option_id,
                "option_label": label,
                "custom_text": custom_text,
                "status": result.get("status"),
                "result": result,
                "summary": result.get("reason") or f"Decision {patch_id} recorded.",
            }
        )

    return commit_decision_patch_application(
        context,
        operation_id=operation_id,
        model=model,
        results=results,
        applied_events=applied_events,
        chat_selections=chat_selections,
        accepted_count=accepted_count,
        noted_count=noted_count,
        rejected_count=rejected_count,
        changed_count=changed_count,
    )


async def _apply_decision_patches_core(
    job_id: str,
    request: DecisionPatchApplyRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_handle: RunOperationHandle | None = None,
) -> dict[str, Any]:
    result = await run_thread_to_completion(
        _apply_decision_patches_transaction,
        job_id,
        request,
        runs_dir=runs_dir,
        sessions_dir=sessions_dir,
        active_runs=active_runs,
        operation_id=(
            operation_handle.operation_id
            if operation_handle is not None
            else f"decision.{job_id}"
        ),
    )
    if operation_handle is not None:
        await operation_handle.begin_finalizing()
    return result


async def apply_decision_patches_core(
    job_id: str,
    request: DecisionPatchApplyRequest,
    *,
    runs_dir: Path,
    sessions_dir: Path,
    active_runs: dict[str, ActiveRun] | None = None,
    operation_registry: RunOperationRegistry,
) -> dict[str, Any]:
    if run_is_active(job_id, active_runs):
        raise HTTPException(
            status_code=409,
            detail="Cannot apply decision patches while the run is still active.",
        )
    async with claim_recorded_run_operation(
        job_id,
        RunOperationKind.DECISION,
        runs_dir=runs_dir,
        registry=operation_registry,
    ) as operation_handle:
        await operation_handle.begin_draining()
        return await _apply_decision_patches_core(
            job_id,
            request,
            runs_dir=runs_dir,
            sessions_dir=sessions_dir,
            active_runs=active_runs,
            operation_handle=operation_handle,
        )


__all__ = ["apply_decision_patches_core", "decision_choices_from_request"]
