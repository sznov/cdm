from __future__ import annotations

from core.operation_loop_result import OperationLoopResult

from harnesses.structured_patch.events import structured_model_event_payload
from harnesses.structured_patch.model_conversion import structured_model_to_working_model
from harnesses.structured_patch.result_building import FinalizationInput, build_async_op_patch_result
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal
from harnesses.structured_patch.runner_operation_state import AsyncOpPatchOperationState
from core.plantuml_structured import render_structured_model_to_plantuml


async def finalize_async_op_patch_run(
    context: HarnessRunContext,
    phase_input: FinalizationInput,
    journal: RunJournal,
    operation_state: AsyncOpPatchOperationState,
) -> OperationLoopResult:
    structured_model = phase_input.post_patch_result.structured_model
    decision_patches = phase_input.post_patch_result.decision_patches
    applied_operations = operation_state.applied_operations
    rejected_operations = operation_state.rejected_operations
    already_satisfied_operations = operation_state.already_satisfied_operations
    deferred_operations = operation_state.deferred_operations
    emit = context.events.emit
    context.config.name_policy.validate_model_names(structured_model)
    working_model = structured_model_to_working_model(structured_model)
    plantuml = render_structured_model_to_plantuml(structured_model)
    plantuml_url = ""
    await emit(
        "structured_model_validated",
        {
            "agent_id": "structuredValidator",
            "entity_count": len(structured_model.entities),
            "relationship_count": len(structured_model.relationships),
            "summary": f"{len(structured_model.entities)} entities, {len(structured_model.relationships)} relationships in final async patch snapshot.",
            **structured_model_event_payload(structured_model),
            "applied_operations": applied_operations,
            "already_satisfied_operations": already_satisfied_operations,
            "rejected_operations": rejected_operations,
            "deferred_operations": deferred_operations,
            "decision_patches": decision_patches,
        },
    )
    await emit("working_model", {"working_model": working_model.model_dump(mode="json"), "model": working_model.model_dump(mode="json")})
    await emit("plantuml_preview", {"plantuml": plantuml, "plantuml_url": plantuml_url})

    return build_async_op_patch_result(
        context,
        phase_input,
        journal,
        operation_state,
        working_model=working_model,
        plantuml=plantuml,
    )


__all__ = ["FinalizationInput", "finalize_async_op_patch_run"]
