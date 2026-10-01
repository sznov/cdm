from __future__ import annotations

import asyncio
from typing import Any

from core.model_call_logger import ModelCallLogger
from backend.services.async_file_work import run_thread_to_completion
from backend.services.correction_language_repair import run_correction_post_patch_language_repair
from backend.services.correction_patch_application import CorrectionPatchApplicationResult
from backend.services.correction_patch_context import FreeformCorrectionContext
from backend.services.correction_transactions import (
    CORRECTION_CHECKPOINT_TRANSACTION,
    CORRECTION_COMPLETION_TRANSACTION,
    CorrectionTransactionCommit,
    commit_correction_model_transaction,
)
from backend.services.run_operation_registry import RunOperationHandle


async def emit_correction_patch_progress(
    *,
    job_id: str,
    context: FreeformCorrectionContext,
    application_result: CorrectionPatchApplicationResult,
) -> None:
    await context.emit(
        "correction_patch_chat_progress",
        {
            "job_id": job_id,
            "accepted_count": application_result.accepted_count,
            "changed_count": application_result.changed_count,
            "rejected_count": application_result.rejected_count,
            "deferred_count": application_result.deferred_count,
            "summary": (
                f"Correction patch operations applied: {application_result.accepted_count} accepted/already satisfied, "
                f"{application_result.changed_count} changed, {application_result.rejected_count} rejected, "
                f"{application_result.deferred_count} deferred."
            ),
        },
    )


async def complete_correction_patch_application(
    *,
    job_id: str,
    context: FreeformCorrectionContext,
    logger: ModelCallLogger,
    raw_output: str,
    operations: list[dict[str, Any]],
    application_result: CorrectionPatchApplicationResult,
    operation_handle: RunOperationHandle,
) -> dict[str, Any]:
    model = application_result.model
    results = application_result.results
    accepted_count = application_result.accepted_count
    changed_count = application_result.changed_count
    rejected_count = application_result.rejected_count
    deferred_count = application_result.deferred_count

    def commit_current_correction_model(
        *,
        operation_type: str,
        summary: str,
        include_snapshot_event: bool,
        completion_payload: dict[str, Any] | None = None,
        language_repair: dict[str, Any] | None = None,
    ) -> CorrectionTransactionCommit:
        return commit_correction_model_transaction(
            run_dir=context.run_dir,
            sessions_dir=context.sessions_dir,
            record=context.record,
            job_id=job_id,
            operation_id=operation_handle.operation_id,
            operation_type=operation_type,
            model=model,
            results=results,
            summary=summary,
            name_policy=context.patch_policy.name_policy,
            language_repair=language_repair,
            include_snapshot_event=include_snapshot_event,
            completion_payload=completion_payload,
        )

    pre_repair_snapshot_payload: dict[str, Any] | None = None
    if changed_count > 0:
        await context.event_recorder.flush()
        pre_repair_commit = await run_thread_to_completion(
            commit_current_correction_model,
            operation_type=CORRECTION_CHECKPOINT_TRANSACTION,
            summary=f"Rendered after {changed_count} correction patch mutation(s), before optional language repair.",
            include_snapshot_event=True,
        )
        pre_repair_snapshot_payload = pre_repair_commit.snapshot_payload
        await context.event_recorder.deliver_committed_records(
            pre_repair_commit.trace_records
        )
        await emit_correction_patch_progress(
            job_id=job_id,
            context=context,
            application_result=application_result,
        )

    language_repair_record: dict[str, Any] | None = None
    repair_eligible = bool(
        context.patch_policy.language_repair_enabled
        and changed_count > 0
        and model.entities
    )
    cancellation_handled = False
    if repair_eligible:
        if await operation_handle.begin_provider_phase():
            try:
                model, language_repair_record = (
                    await run_correction_post_patch_language_repair(
                        job_id=job_id,
                        provider=context.provider,
                        client=context.client,
                        logger=logger,
                        specification=context.specification,
                        model=model,
                        emit=context.emit,
                    )
                )
            except asyncio.CancelledError:
                detail = (
                    "Structured language repair was interrupted after "
                    "correction patch operations were applied."
                )
                language_repair_record = {
                    "applied_count": 0,
                    "interrupted": True,
                    "error": detail,
                }
                await context.emit(
                    "structured_language_repair_applied",
                    {
                        "job_id": job_id,
                        "agent_id": "structuredLanguageRepair",
                        "stage": "correction_post_patch_language_repair",
                        **language_repair_record,
                        "summary": detail,
                    },
                )
            cancellation_handled = bool(
                language_repair_record.get("interrupted")
            )
        else:
            detail = (
                "Structured language repair was skipped because cancellation "
                "was requested while deterministic correction persistence "
                "was completing."
            )
            language_repair_record = {
                "applied_count": 0,
                "interrupted": True,
                "skipped": True,
                "reason": "cancellation_requested_before_provider_reentry",
                "error": detail,
            }
            cancellation_handled = True
            await context.emit(
                "structured_language_repair_skipped",
                {
                    "job_id": job_id,
                    "agent_id": "structuredLanguageRepair",
                    "stage": "correction_post_patch_language_repair",
                    **language_repair_record,
                    "summary": detail,
                },
            )

    try:
        finalizing = await operation_handle.begin_finalizing(
            cancellation_handled=cancellation_handled,
        )
    except asyncio.CancelledError:
        cancellation_handled = True
        finalizing = await operation_handle.begin_finalizing(
            cancellation_handled=True,
        )
    if not finalizing:
        cancellation_handled = True
        await operation_handle.begin_finalizing(
            cancellation_handled=True,
        )

    emit_final_snapshot = bool(
        changed_count > 0
        and (
            pre_repair_snapshot_payload is None
            or (
                language_repair_record is not None
                and (
                    language_repair_record.get("applied_count", 0) > 0
                    or bool(language_repair_record.get("error"))
                )
            )
        )
    )
    done_payload_without_patches = {
        "job_id": job_id,
        "accepted_count": accepted_count,
        "changed_count": changed_count,
        "rejected_count": rejected_count,
        "deferred_count": deferred_count,
        "language_repair": language_repair_record,
        "summary": (
            f"Correction patch chat complete: {accepted_count} accepted/already satisfied, "
            f"{changed_count} changed, {rejected_count} rejected, {deferred_count} deferred."
        ),
    }
    await context.event_recorder.flush()
    final_commit = await run_thread_to_completion(
        commit_current_correction_model,
        operation_type=CORRECTION_COMPLETION_TRANSACTION,
        summary=f"Rendered after {changed_count} correction patch mutation(s).",
        include_snapshot_event=emit_final_snapshot,
        completion_payload=done_payload_without_patches,
        language_repair=language_repair_record,
    )
    await context.event_recorder.deliver_committed_records(
        final_commit.trace_records
    )
    snapshot_payload = final_commit.snapshot_payload
    patches = final_commit.decision_patches
    done_payload = final_commit.completion_payload
    if done_payload is None:  # pragma: no cover - completion contract
        raise RuntimeError("Correction completion transaction omitted its payload.")
    return {
        **done_payload,
        "raw_output": raw_output,
        "operations": operations,
        "results": results,
        "decision_patches": patches,
        **snapshot_payload,
    }


__all__ = ["complete_correction_patch_application", "emit_correction_patch_progress"]
