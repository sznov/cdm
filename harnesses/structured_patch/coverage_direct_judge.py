from __future__ import annotations

from typing import Any

from harnesses.structured_patch.coverage_phase_types import (
    CoverageCriticPhaseResult,
    RunnerCoveragePhaseInput,
)
from harnesses.structured_patch.decision_identifier_context import propose_identifier_context_decision_patches
from harnesses.structured_patch.decision_merge import merge_decision_patches
from harnesses.structured_patch.runner_context import HarnessRunContext, RunJournal


def direct_microop_judge_finding(draft_issue_hard_findings: list[dict[str, str]]) -> dict[str, str]:
    return {
        "id": "F1",
        "severity": "high",
        "kind": "other",
        "plan_task_id": "T1",
        "summary": "Judge the validated draft against the full specification and emit only necessary micro-operations.",
        "evidence": "",
        "suggested_change": (
            "Check for spec-grounded semantic errors, conflated concepts, association entities with "
            "their own facts, repeated attributes that represent the same concept, lookup candidates "
            "represented as strings, scalar attributes that refer to modeled concepts, grouped "
            "multi-field value concepts such as addresses/residences/locations, missing relationships, "
            "wrong multiplicities, identifier issues, duplicated information, normalization gaps, "
            "inheritance gaps, and unsupported artifacts. Prefer maximal spec-grounded normalization. "
            "Emit no operations when the current draft is already adequate."
        ),
    }


async def run_direct_microop_judge_phase(
    context: HarnessRunContext,
    phase_input: RunnerCoveragePhaseInput,
    journal: RunJournal,
) -> CoverageCriticPhaseResult:
    initial_phase = phase_input.initial_phase
    structured_model = initial_phase.structured_model
    infer_implicit_identifiers = context.config.infer_implicit_identifiers
    draft_model_issues = initial_phase.draft_model_issues
    draft_issue_decision_patches = initial_phase.draft_issue_decision_patches
    draft_issue_hard_findings = initial_phase.draft_issue_hard_findings
    operation_history = journal.operation_history
    emit = context.events.emit
    checkpoint = context.events.checkpoint
    name_policy = context.config.name_policy
    direct_microop_finding = direct_microop_judge_finding(draft_issue_hard_findings)
    findings = [*draft_issue_hard_findings, direct_microop_finding]
    if infer_implicit_identifiers:
        decision_patches = merge_decision_patches(
            draft_issue_decision_patches,
            propose_identifier_context_decision_patches(
                structured_model,
                name_policy=name_policy,
            ),
            name_policy=name_policy,
        )
    else:
        decision_patches = merge_decision_patches(
            draft_issue_decision_patches,
            name_policy=name_policy,
        )
    operation_history.append(
        {
            "iteration": 3,
            "batch_attempt": 1,
            "accepted": [{"op": "DIRECT_MICROOP_JUDGE", "finding_count": len(findings)}],
            "rejected": [],
            "focus": "Use the micro-operation clerk as the direct judge/validator.",
            "feedback": "",
        }
    )
    await emit(
        "plan_coverage_critic_result",
        {
            "agent_id": "patchOperationClerk",
            "finding_count": len(findings),
            "critic_finding_count": 0,
            "draft_hard_finding_count": len(draft_issue_hard_findings),
            "findings": findings,
            "summary": "Coverage critic skipped; micro-operation clerk will judge the draft directly.",
        },
    )
    if decision_patches:
        await emit(
            "decision_patches",
            {
                "agent_id": "patchOperationClerk",
                "decision_patches": decision_patches,
                "summary": f"{len(decision_patches)} user decision patch(es) available.",
            },
        )
    await checkpoint(
        "async-op-patch-after-coverage-critic",
        {
            "structured_model": structured_model.model_dump(mode="json"),
            "draft_model_issues": draft_model_issues,
            "draft_issue_decision_patches": draft_issue_decision_patches,
            "draft_issue_hard_findings": draft_issue_hard_findings,
            "findings": findings,
            "decision_patches": decision_patches,
        },
        "Async Operation Patch direct micro-op judge checkpoint written.",
    )
    return CoverageCriticPhaseResult(findings=findings, decision_patches=decision_patches)


__all__ = ["direct_microop_judge_finding", "run_direct_microop_judge_phase"]
