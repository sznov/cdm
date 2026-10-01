from __future__ import annotations

from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, assert_never

from core.model_client import TextModelClient
from core.operation_loop_result import OperationLoopResult
from harnesses.contracts import (
    DirectBaselineEffectiveConfig,
    EffectiveHarnessRunSpec,
    HarnessExecutorId,
    StructuredPatchEffectiveConfig,
)
from harnesses.direct_baseline.app_runner import run_direct_baseline_app_harness
from harnesses.structured_patch.correction_policy import (
    LEGACY_POSTHOC_CORRECTION_POLICY,
    REFINED_CORRECTION_POLICY,
)
from harnesses.structured_patch.correction_templates import (
    SINGLE_CONSERVATIVE_CORRECTION_TEMPLATE_ID,
)
from harnesses.structured_patch.required_correction_phase import (
    preexecution_required_correction_error,
    required_correction_configuration_error,
    run_required_correction_phase,
)
from harnesses.structured_patch.required_correction_types import RequiredCorrectionPhaseInput
from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    UNICODE_NFKC_NAME_POLICY,
)
from harnesses.structured_patch.runner import run_async_op_patch_model


HarnessEventSink = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class HarnessExecutionRequest:
    """Runtime adapters plus one already-materialized catalog specification."""

    spec: EffectiveHarnessRunSpec
    specification: str
    client: TextModelClient
    job_id: str
    model_call_log_dir: Path | None = None
    resume_state: dict[str, Any] | None = None
    on_event: HarnessEventSink | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "spec", self.spec.detached_copy())
        object.__setattr__(self, "resume_state", deepcopy(self.resume_state))


@dataclass(frozen=True, slots=True)
class HarnessExecutionResult:
    result: OperationLoopResult
    correction_sequence: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "correction_sequence", deepcopy(self.correction_sequence))


def _structured_max_attempts(config: StructuredPatchEffectiveConfig) -> int:
    configured = config.max_attempts if config.max_attempts is not None else config.batch_retries
    return max(1, int(configured))


async def execute_materialized_harness(
    request: HarnessExecutionRequest,
) -> HarnessExecutionResult:
    """Dispatch a closed built-in executor without consulting the live catalog."""

    spec = request.spec
    executor_id = spec.executor_id
    name_policy = (
        UNICODE_NFKC_NAME_POLICY
        if executor_id == HarnessExecutorId.STRUCTURED_PATCH_REFINED
        else LEGACY_ASCII_NAME_POLICY
    )

    if executor_id == HarnessExecutorId.STRUCTURED_PATCH_LEGACY:
        config = spec.effective_config
        if not isinstance(config, StructuredPatchEffectiveConfig):
            raise TypeError("Legacy structured-patch executor requires structured-patch configuration.")
        result = await run_async_op_patch_model(
            specification=request.specification,
            client=request.client,
            max_attempts=_structured_max_attempts(config),
            infer_implicit_identifiers=config.infer_implicit_identifiers,
            structured_language_repair=config.language_repair,
            direct_microop_judge=config.direct_microop_judge,
            name_policy=name_policy,
            job_id=request.job_id,
            model_call_log_dir=request.model_call_log_dir,
            resume_state=request.resume_state,
            on_event=request.on_event,
        )
        if not config.auto_correction_sequence:
            return HarnessExecutionResult(result=result)
        phase_result = await run_required_correction_phase(
            phase_input=RequiredCorrectionPhaseInput(
                specification=request.specification,
                result=result,
                correction_template_id=(
                    config.correction_template_id or SINGLE_CONSERVATIVE_CORRECTION_TEMPLATE_ID
                ),
                max_operations=config.max_correction_operations,
            ),
            client=request.client,
            model_call_log_dir=request.model_call_log_dir,
            transport_retries=None,
            policy=LEGACY_POSTHOC_CORRECTION_POLICY,
            on_event=request.on_event,
        )
        return HarnessExecutionResult(
            result=phase_result.result,
            correction_sequence=phase_result.correction_sequence,
        )

    if executor_id == HarnessExecutorId.STRUCTURED_PATCH_REFINED:
        config = spec.effective_config
        if not isinstance(config, StructuredPatchEffectiveConfig):
            raise TypeError("Refined structured-patch executor requires structured-patch configuration.")
        policy = REFINED_CORRECTION_POLICY
        correction_template_id = (
            config.correction_template_id or SINGLE_CONSERVATIVE_CORRECTION_TEMPLATE_ID
        )
        configuration_error = required_correction_configuration_error(correction_template_id)
        if configuration_error is not None:
            raise preexecution_required_correction_error(
                correction_template_id=correction_template_id,
                policy=policy,
                error=configuration_error,
            )
        result = await run_async_op_patch_model(
            specification=request.specification,
            client=request.client,
            max_attempts=_structured_max_attempts(config),
            infer_implicit_identifiers=config.infer_implicit_identifiers,
            structured_language_repair=config.language_repair,
            direct_microop_judge=config.direct_microop_judge,
            name_policy=name_policy,
            job_id=request.job_id,
            model_call_log_dir=request.model_call_log_dir,
            resume_state=request.resume_state,
            on_event=request.on_event,
        )
        phase_result = await run_required_correction_phase(
            phase_input=RequiredCorrectionPhaseInput(
                specification=request.specification,
                result=result,
                correction_template_id=correction_template_id,
                max_operations=config.max_correction_operations,
            ),
            client=request.client,
            model_call_log_dir=request.model_call_log_dir,
            transport_retries=None,
            policy=policy,
            on_event=request.on_event,
        )
        return HarnessExecutionResult(
            result=phase_result.result,
            correction_sequence=phase_result.correction_sequence,
        )

    if executor_id == HarnessExecutorId.DIRECT_BASELINE:
        config = spec.effective_config
        if not isinstance(config, DirectBaselineEffectiveConfig):
            raise TypeError("Direct-baseline executor requires direct-baseline configuration.")
        result = await run_direct_baseline_app_harness(
            specification=request.specification,
            client=request.client,
            job_id=request.job_id,
            model_call_log_dir=request.model_call_log_dir,
            prompt_profile_id=config.prompt_profile,
            max_attempts=max(1, int(config.batch_retries)),
            on_event=request.on_event,
        )
        return HarnessExecutionResult(result=result)

    assert_never(executor_id)


__all__ = [
    "HarnessEventSink",
    "HarnessExecutionRequest",
    "HarnessExecutionResult",
    "execute_materialized_harness",
]
