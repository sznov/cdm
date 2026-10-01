from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from harnesses.contracts import EffectiveHarnessRunSpec
from harnesses.provenance import (
    ProviderExecutionIdentity,
    canonical_sha256,
    endpoint_class_for_provider,
)


@dataclass(frozen=True, slots=True, init=False)
class PreparedRun:
    """The single immutable value accepted by persistence and scheduling."""

    _effective_harness_run_spec: EffectiveHarnessRunSpec
    _provider_execution: ProviderExecutionIdentity
    specification: str
    specification_sha256: str
    session_id: str | None
    retry_of_job_id: str | None
    resume_from_job_id: str | None
    resume_trace_index: int | None
    _resume_state: dict[str, Any] | None
    _resume_checkpoint_bytes: bytes | None
    runtime_harness_name: str
    runtime_endpoint: str
    _runtime_harness_snapshot: dict[str, Any]

    def __init__(
        self,
        *,
        effective_harness_run_spec: EffectiveHarnessRunSpec,
        provider_execution: ProviderExecutionIdentity,
        specification: str,
        session_id: str | None,
        retry_of_job_id: str | None = None,
        resume_from_job_id: str | None = None,
        resume_trace_index: int | None = None,
        resume_state: dict[str, Any] | None = None,
        resume_checkpoint_bytes: bytes | None = None,
        runtime_harness_name: str,
        runtime_endpoint: str,
        runtime_harness_snapshot: dict[str, Any],
    ) -> None:
        detached_specification = str(specification)
        binding = effective_harness_run_spec.model_bindings["default"]
        if (
            provider_execution.provider_id != binding.provider
            or provider_execution.model_id != binding.model
            or provider_execution.binding_sha256 != canonical_sha256(binding)
        ):
            raise ValueError("Prepared provider identity does not match the effective model binding.")
        if not binding.base_url:
            raise ValueError("Prepared runs require a frozen provider endpoint.")
        if provider_execution.endpoint_class != endpoint_class_for_provider(
            binding.provider,
            binding.base_url,
        ):
            raise ValueError("Prepared provider endpoint class does not match the effective model binding.")
        object.__setattr__(
            self,
            "_effective_harness_run_spec",
            effective_harness_run_spec.detached_copy(),
        )
        object.__setattr__(self, "_provider_execution", provider_execution.model_copy(deep=True))
        object.__setattr__(self, "specification", detached_specification)
        object.__setattr__(
            self,
            "specification_sha256",
            hashlib.sha256(detached_specification.encode("utf-8")).hexdigest(),
        )
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "retry_of_job_id", retry_of_job_id)
        object.__setattr__(self, "resume_from_job_id", resume_from_job_id)
        object.__setattr__(self, "resume_trace_index", resume_trace_index)
        object.__setattr__(self, "_resume_state", deepcopy(resume_state))
        object.__setattr__(
            self,
            "_resume_checkpoint_bytes",
            bytes(resume_checkpoint_bytes) if resume_checkpoint_bytes is not None else None,
        )
        object.__setattr__(self, "runtime_harness_name", str(runtime_harness_name))
        object.__setattr__(self, "runtime_endpoint", str(runtime_endpoint))
        object.__setattr__(self, "_runtime_harness_snapshot", deepcopy(runtime_harness_snapshot))

    @property
    def effective_harness_run_spec(self) -> EffectiveHarnessRunSpec:
        return self._effective_harness_run_spec.detached_copy()

    @property
    def provider_execution(self) -> ProviderExecutionIdentity:
        return self._provider_execution.model_copy(deep=True)

    @property
    def resume_state(self) -> dict[str, Any] | None:
        return deepcopy(self._resume_state)

    @property
    def resume_checkpoint_bytes(self) -> bytes | None:
        value = self._resume_checkpoint_bytes
        return bytes(value) if value is not None else None

    @property
    def runtime_harness_snapshot(self) -> dict[str, Any]:
        return deepcopy(self._runtime_harness_snapshot)

    @property
    def runtime_harness_id(self) -> str:
        return self._effective_harness_run_spec.harness_id


__all__ = ["PreparedRun"]
