from __future__ import annotations

import asyncio
from collections.abc import MutableMapping

import httpx

from backend.services.active_run_registry import ActiveRun
from backend.services.async_file_work import run_thread_to_completion
from backend.services.correction_clients import model_call_error_detail
from backend.services.run_stream_events import RunStreamEventBus
from backend.services.run_stream_records import RunStreamRecordContext
from backend.services.run_stream_results import persist_run_result_transaction
from backend.services.run_worker_outcome import RunWorkerOutcome
from core.config_safety import safe_exception_detail
from core.model_bindings import normalize_model_bindings
from core.providers.factory import build_text_model_client
from harnesses.execution import HarnessExecutionRequest, execute_materialized_harness
from harnesses.structured_patch.required_correction_types import RequiredCorrectionPhaseError


async def run_stream_worker(
    record_context: RunStreamRecordContext,
    *,
    event_bus: RunStreamEventBus,
    active_runs: MutableMapping[str, ActiveRun],
) -> RunWorkerOutcome:
    prepared_run = record_context.prepared_run
    job_id = record_context.job_id
    _ = active_runs
    try:
        spec = record_context.effective_harness_run_spec
        default_binding = normalize_model_bindings(
            spec.model_dump(mode="json")["model_bindings"]
        )["default"]
        provider_id = str(default_binding["provider"])
        provider_options = (
            default_binding.get("provider_options")
            if isinstance(default_binding.get("provider_options"), dict)
            else {}
        )
        if provider_id == "nvidia_nim":
            provider_options = {
                **provider_options,
                "catalog_entries": record_context.provider_execution.execution_catalog_entries(),
            }
        client = build_text_model_client(
            provider=provider_id,
            model=str(default_binding["model"]),
            base_url=default_binding.get("base_url"),
            max_completion_tokens=default_binding.get("max_completion_tokens"),
            temperature=default_binding.get("temperature"),
            top_p=default_binding.get("top_p"),
            timeout_seconds=float(default_binding.get("timeout_seconds") or 600.0),
            reasoning_effort=default_binding.get("reasoning_effort"),
            provider_options=provider_options,
            model_parameters=(
                default_binding.get("model_parameters")
                if isinstance(default_binding.get("model_parameters"), dict)
                else None
            ),
        )
        try:
            execution = await execute_materialized_harness(
                HarnessExecutionRequest(
                    spec=spec,
                    specification=prepared_run.specification,
                    client=client,
                    job_id=job_id,
                    model_call_log_dir=record_context.model_call_log_dir,
                    resume_state=record_context.resume_state,
                    on_event=event_bus.emit,
                )
            )
            persisted = await run_thread_to_completion(
                persist_run_result_transaction,
                record_context,
                result=execution.result,
                correction_sequence=execution.correction_sequence,
            )
            if persisted.result_payload is None:  # pragma: no cover - result contract
                raise TypeError("Successful harness execution must persist a result.")
            return RunWorkerOutcome.completed(persisted.result_payload)
        except RequiredCorrectionPhaseError as exc:
            persisted = await run_thread_to_completion(
                persist_run_result_transaction,
                record_context,
                result=exc.fallback_result,
                correction_sequence=exc.correction_sequence,
            )
            return RunWorkerOutcome.failed(
                safe_exception_detail(exc),
                result_payload=persisted.result_payload,
                correction_sequence=persisted.correction_sequence,
            )
    except asyncio.CancelledError:
        interruption = event_bus.interrupted_payload()
        if interruption is not None:
            await event_bus.emit("model_generation_interrupted", interruption)
        raise
    except httpx.HTTPStatusError as exc:
        provider_id = record_context.effective_harness_run_spec.model_bindings["default"].provider
        detail = model_call_error_detail(str(provider_id), exc)
        return RunWorkerOutcome.failed(detail)
    except Exception as exc:
        detail = safe_exception_detail(exc)
        return RunWorkerOutcome.failed(detail)
    finally:
        event_bus.end()


__all__ = ["run_stream_worker"]
