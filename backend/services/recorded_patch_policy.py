from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harnesses.contracts import EffectiveHarnessRunSpec, HarnessExecutorId
from harnesses.structured_patch.correction_policy import (
    CorrectionOperationGuard,
    LEGACY_POSTHOC_CORRECTION_POLICY,
    REFINED_CORRECTION_POLICY,
    stated_identifier_patch_guard_reason,
)
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_prompts import (
    PATCH_OPERATION_CLERK_USER_TEMPLATE,
    UNICODE_NFKC_PATCH_OPERATION_CLERK_USER_TEMPLATE,
)


@dataclass(frozen=True, slots=True)
class RecordedPatchPolicy:
    """Explicit-operation behavior sealed by a run's materialized protocol."""

    executor_id: HarnessExecutorId
    name_policy: StructuredNamePolicy
    operation_guard: CorrectionOperationGuard | None
    language_repair_enabled: bool
    prompt_template: str


class RecordedPatchPolicyError(ValueError):
    pass


_KNOWN_RECORDED_PROTOCOLS = frozenset(
    {
        (
            "gemma4-tuned-final",
            "gemma4-tuned-final-20260524",
            HarnessExecutorId.STRUCTURED_PATCH_LEGACY,
        ),
        (
            "structured-patch-refined",
            "structured-patch-refined-v2",
            HarnessExecutorId.STRUCTURED_PATCH_REFINED,
        ),
        (
            "direct-baseline-schema-only-v1",
            "direct-baseline-schema-only-v1-20260616",
            HarnessExecutorId.DIRECT_BASELINE,
        ),
        (
            "direct-baseline-structured-draft-with-issues",
            "direct-baseline-structured-draft-with-issues-20260616",
            HarnessExecutorId.DIRECT_BASELINE,
        ),
    }
)


def recorded_patch_policy(record: dict[str, Any]) -> RecordedPatchPolicy:
    try:
        spec = EffectiveHarnessRunSpec.model_validate(record.get("effective_harness_run_spec"))
    except (TypeError, ValueError) as exc:
        raise RecordedPatchPolicyError(
            "Run has no valid persisted effective harness specification."
        ) from exc
    protocol_identity = (
        spec.harness_id,
        spec.definition_revision,
        spec.executor_id,
    )
    if protocol_identity not in _KNOWN_RECORDED_PROTOCOLS:
        raise RecordedPatchPolicyError(
            "Run records an unsupported persisted harness protocol identity: "
            f"{spec.harness_id!r} at revision {spec.definition_revision!r} "
            f"with executor {spec.executor_id.value!r}."
        )
    language_repair_enabled = bool(spec.effective_config.language_repair)

    if spec.executor_id == HarnessExecutorId.STRUCTURED_PATCH_LEGACY:
        phase_policy = LEGACY_POSTHOC_CORRECTION_POLICY
        # The legacy executor's post-hoc phase predates the refined
        # whole-model language pass. Explicit corrections must follow that
        # recorded phase rather than the broader runtime-config projection.
        language_repair_enabled = False
    elif spec.executor_id == HarnessExecutorId.STRUCTURED_PATCH_REFINED:
        phase_policy = REFINED_CORRECTION_POLICY
        language_repair_enabled = False
    else:
        # Direct baselines historically use the explicit patch service's
        # legacy-ASCII identifier-veto behavior after producing a structured result.
        return RecordedPatchPolicy(
            executor_id=spec.executor_id,
            name_policy=LEGACY_ASCII_NAME_POLICY,
            operation_guard=stated_identifier_patch_guard_reason,
            language_repair_enabled=language_repair_enabled,
            prompt_template=PATCH_OPERATION_CLERK_USER_TEMPLATE,
        )

    return RecordedPatchPolicy(
        executor_id=spec.executor_id,
        name_policy=phase_policy.name_policy,
        operation_guard=phase_policy.operation_guard,
        language_repair_enabled=language_repair_enabled,
        prompt_template=(
            UNICODE_NFKC_PATCH_OPERATION_CLERK_USER_TEMPLATE
            if phase_policy.name_policy.preserves_unicode
            else PATCH_OPERATION_CLERK_USER_TEMPLATE
        ),
    )


__all__ = [
    "RecordedPatchPolicy",
    "RecordedPatchPolicyError",
    "recorded_patch_policy",
]
