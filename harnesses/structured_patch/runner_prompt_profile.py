from __future__ import annotations

from dataclasses import dataclass

from harnesses.structured_patch.coverage_prompts import (
    LEGACY_PLAN_COVERAGE_CRITIC_USER_TEMPLATE,
    PLAN_COVERAGE_CRITIC_USER_TEMPLATE,
)
from harnesses.structured_patch.draft_prompts import (
    LEGACY_SIMPLE_DRAFT_USER_TEMPLATE,
    SIMPLE_DRAFT_USER_TEMPLATE,
    UNICODE_NFKC_SIMPLE_DRAFT_USER_TEMPLATE,
)
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_prompts import (
    LEGACY_PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
    LEGACY_PATCH_OPERATION_CLERK_USER_TEMPLATE,
    PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
    PATCH_OPERATION_CLERK_USER_TEMPLATE,
    UNICODE_NFKC_PATCH_OPERATION_CLERK_USER_TEMPLATE,
)


STRUCTURED_PATCH_PROMPT_PROFILE_REVISIONS = {
    "legacy": "structured-patch-prompts-legacy-v1",
    "refined": "structured-patch-prompts-refined-v1",
    "refined_v2_unicode_nfkc": "structured-patch-prompts-refined-v2-unicode-nfkc-v1",
}


@dataclass(frozen=True, slots=True)
class AsyncOpPatchPromptProfile:
    profile_id: str
    profile_revision: str
    draft_user_template: str
    coverage_critic_user_template: str
    patch_clerk_system_prompt: str
    patch_clerk_user_template: str
    correction_patch_system_prompt: str
    correction_patch_user_template: str


def async_op_patch_prompt_profile(
    *,
    direct_microop_judge: bool,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> AsyncOpPatchPromptProfile:
    if name_policy.preserves_unicode:
        profile_id = "refined_v2_unicode_nfkc"
        return AsyncOpPatchPromptProfile(
            profile_id=profile_id,
            profile_revision=STRUCTURED_PATCH_PROMPT_PROFILE_REVISIONS[profile_id],
            draft_user_template=UNICODE_NFKC_SIMPLE_DRAFT_USER_TEMPLATE,
            coverage_critic_user_template=PLAN_COVERAGE_CRITIC_USER_TEMPLATE,
            patch_clerk_system_prompt=PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
            patch_clerk_user_template=UNICODE_NFKC_PATCH_OPERATION_CLERK_USER_TEMPLATE,
            correction_patch_system_prompt=PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
            correction_patch_user_template=UNICODE_NFKC_PATCH_OPERATION_CLERK_USER_TEMPLATE,
        )
    if direct_microop_judge:
        profile_id = "refined"
        return AsyncOpPatchPromptProfile(
            profile_id=profile_id,
            profile_revision=STRUCTURED_PATCH_PROMPT_PROFILE_REVISIONS[profile_id],
            draft_user_template=SIMPLE_DRAFT_USER_TEMPLATE,
            coverage_critic_user_template=PLAN_COVERAGE_CRITIC_USER_TEMPLATE,
            patch_clerk_system_prompt=PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
            patch_clerk_user_template=PATCH_OPERATION_CLERK_USER_TEMPLATE,
            correction_patch_system_prompt=PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
            correction_patch_user_template=PATCH_OPERATION_CLERK_USER_TEMPLATE,
        )
    profile_id = "legacy"
    return AsyncOpPatchPromptProfile(
        profile_id=profile_id,
        profile_revision=STRUCTURED_PATCH_PROMPT_PROFILE_REVISIONS[profile_id],
        draft_user_template=LEGACY_SIMPLE_DRAFT_USER_TEMPLATE,
        coverage_critic_user_template=LEGACY_PLAN_COVERAGE_CRITIC_USER_TEMPLATE,
        patch_clerk_system_prompt=LEGACY_PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
        patch_clerk_user_template=LEGACY_PATCH_OPERATION_CLERK_USER_TEMPLATE,
        correction_patch_system_prompt=PATCH_OPERATION_CLERK_SYSTEM_PROMPT,
        correction_patch_user_template=PATCH_OPERATION_CLERK_USER_TEMPLATE,
    )


__all__ = [
    "AsyncOpPatchPromptProfile",
    "STRUCTURED_PATCH_PROMPT_PROFILE_REVISIONS",
    "async_op_patch_prompt_profile",
]
