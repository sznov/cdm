from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harnesses.structured_patch.language_repair_pass import run_structured_language_repair_pass
from harnesses.structured_patch.patch_application_phase import StructuredPatchBatchApplier
from harnesses.structured_patch.runner_decision_state import rescan_identifier_context_decisions
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal
from harnesses.structured_patch.runner_operation_state import AsyncOpPatchOperationState
from harnesses.structured_patch.validation import run_post_patch_hierarchy_identity_validation
from core.schemas import StructuredModel


@dataclass(slots=True)
class PostPatchAdjustmentResult:
    structured_model: StructuredModel
    decision_patches: list[dict[str, Any]]


async def run_post_patch_adjustments(
    context: HarnessRunContext,
    patch_applier: StructuredPatchBatchApplier,
    journal: RunJournal,
    operation_state: AsyncOpPatchOperationState,
) -> PostPatchAdjustmentResult:
    specification = context.specification
    structured_model = patch_applier.model
    decision_patches = patch_applier.decision_patches
    structured_language_repair = context.config.structured_language_repair
    infer_implicit_identifiers = context.config.infer_implicit_identifiers
    applied_operations = operation_state.applied_operations
    emit = context.events.emit
    emit_partial_snapshot = context.events.emit_partial_snapshot
    if structured_language_repair and structured_model.entities and applied_operations:
        structured_model, post_patch_language_repair = await run_structured_language_repair_pass(
            specification=specification,
            structured_model=structured_model,
            client=context.client,
            logger=context.logger,
            harness="async-op-patch-model",
            stage="post_patch_language_repair",
            title="Post-patch language repair prompt",
            prompt_summary="Patched async model resolved into a name-only language repair prompt.",
            start_summary="Checking patch-produced names against the specification language.",
            iteration=5,
            emit=emit,
            input_prompts=journal.input_prompts,
            operation_history=journal.operation_history,
            usage_steps=journal.usage_steps,
            transport_retries=context.config.model_calls.transport_retries,
        )
        if post_patch_language_repair.get("applied_count", 0) > 0:
            await emit_partial_snapshot(
                structured_model,
                "Rendered after post-patch language repair.",
                {
                    "status": "accepted",
                    "op": {"op": "STRUCTURED_LANGUAGE_REPAIR", "stage": "post_patch_language_repair"},
                    "language_repair": post_patch_language_repair,
                    "reason": "Post-patch language repair applied.",
                },
            )

    if structured_model.entities:
        decision_patches, _post_patch_hierarchy_event = await run_post_patch_hierarchy_identity_validation(
            structured_model=structured_model,
            decision_patches=decision_patches,
            emit=emit,
            name_policy=context.config.name_policy,
        )

    if infer_implicit_identifiers:
        decision_patches, decision_patches_changed = rescan_identifier_context_decisions(
            decision_patches=decision_patches,
            structured_model=structured_model,
            name_policy=context.config.name_policy,
        )
        if decision_patches_changed:
            if decision_patches:
                await emit(
                    "decision_patches",
                    {
                        "agent_id": "incrementalOpApplier",
                        "decision_patches": decision_patches,
                        "summary": f"{len(decision_patches)} user decision patch(es) available after patch operations.",
                    },
                )

    return PostPatchAdjustmentResult(
        structured_model=structured_model,
        decision_patches=decision_patches,
    )


__all__ = [
    "PostPatchAdjustmentResult",
    "run_post_patch_adjustments",
]
