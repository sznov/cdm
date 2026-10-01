from __future__ import annotations

import secrets
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.api.settings import (
    RUN_DECISION_PATCHES_FILENAME,
    RUN_RECORD_FILENAME,
    SESSION_RECORD_FILENAME,
)
from backend.persistence.common import utc_now_iso
from backend.persistence.locks import run_lock, session_lock
from backend.persistence.post_run_transactions import (
    POST_RUN_RESULT_TRANSACTION_FIELD,
    PostRunTargetPayload,
    PostRunTraceEventPayload,
    PostRunTransactionResult,
    execute_post_run_transaction,
    post_run_json_bytes,
    post_run_payload_sha256,
)
from backend.persistence.result_records import (
    prepare_result_record_payload,
    read_result_record,
    result_derived_artifact_values,
)
from backend.persistence.run_record_integrity import (
    read_canonical_run_record,
    validate_canonical_run_record,
)
from backend.persistence.run_records import summarize_run_record
from backend.persistence.session_paths import session_record_path
from backend.persistence.session_record_integrity import (
    read_canonical_session_record,
    validate_canonical_session_record,
)
from backend.services.decision_patches import (
    decision_patches_for_transaction,
    merge_decision_patches,
    sorted_decision_patches,
)
from core.plantuml_structured import render_structured_model_to_plantuml
from core.schemas import StructuredModel, validate_structured_model_links
from harnesses.structured_patch.model_conversion import (
    structured_model_to_working_model,
)
from harnesses.structured_patch.name_policy import StructuredNamePolicy


CORRECTION_CHECKPOINT_TRANSACTION = "correction_checkpoint"
CORRECTION_COMPLETION_TRANSACTION = "correction_completion"


@dataclass(frozen=True, slots=True)
class CorrectionTransactionCommit:
    transaction_id: str
    snapshot_payload: dict[str, Any]
    decision_patches: list[dict[str, Any]]
    completion_payload: dict[str, Any] | None
    result_payload: dict[str, Any]
    run_record: dict[str, Any]
    trace_records: tuple[dict[str, Any], ...]


def _transaction_id(operation_id: str, operation_type: str) -> str:
    return f"{operation_id}.{operation_type}.{secrets.token_hex(8)}"


def _artifact_bytes(value: dict[str, Any] | list[Any] | str) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    return post_run_json_bytes(value)


def _snapshot_payload(
    *,
    model: StructuredModel,
    results: list[dict[str, Any]],
    summary: str,
    language_repair: dict[str, Any] | None,
    created_at_utc: str,
) -> dict[str, Any]:
    working_model = structured_model_to_working_model(model)
    payload: dict[str, Any] = {
        "agent_id": "asyncPlantumlRenderer",
        "diagram_version": int(
            datetime.fromisoformat(
                created_at_utc.replace("Z", "+00:00")
            ).timestamp()
        ),
        "summary": summary,
        "structured_model": model.model_dump(mode="json"),
        "model_snapshot": working_model.model_dump(mode="json"),
        "plantuml": render_structured_model_to_plantuml(model),
        "plantuml_url": "",
        "correction_patch_results": results,
    }
    if language_repair is not None:
        payload["language_repair"] = language_repair
    return payload


def _session_target(
    *,
    session_id: str,
    sessions_dir: Path,
    transaction_id: str,
    run_id: str,
    message_id: str,
    content: str,
    created_at_utc: str,
) -> bytes:
    path = session_record_path(session_id, sessions_dir=sessions_dir)
    record = read_canonical_session_record(path, sessions_dir=sessions_dir)
    messages = (
        list(record.get("chat_messages") or [])
        if isinstance(record.get("chat_messages"), list)
        else []
    )
    for message in messages:
        if not isinstance(message, dict) or message.get("id") != message_id:
            continue
        if (
            message.get("post_run_transaction_id") == transaction_id
            and message.get("post_run_run_id") == run_id
            and message.get("content") == content
        ):
            return post_run_json_bytes(record)
        raise RuntimeError("Transaction chat identity is already occupied.")
    messages.append(
        {
            "id": message_id,
            "role": "assistant",
            "kind": "correction",
            "content": content,
            "created_at_utc": created_at_utc,
            "post_run_transaction_id": transaction_id,
            "post_run_run_id": run_id,
        }
    )
    record["chat_messages"] = messages
    record["updated_at_utc"] = created_at_utc
    return post_run_json_bytes(validate_canonical_session_record(record))


def commit_correction_model_transaction(
    *,
    run_dir: Path,
    sessions_dir: Path,
    record: dict[str, Any],
    job_id: str,
    operation_id: str,
    operation_type: str,
    model: StructuredModel,
    results: list[dict[str, Any]],
    summary: str,
    name_policy: StructuredNamePolicy,
    include_snapshot_event: bool,
    completion_payload: dict[str, Any] | None = None,
    language_repair: dict[str, Any] | None = None,
    transaction_id: str | None = None,
) -> CorrectionTransactionCommit:
    """Commit one correction checkpoint or completion as a roll-forward unit."""

    if operation_type not in {
        CORRECTION_CHECKPOINT_TRANSACTION,
        CORRECTION_COMPLETION_TRANSACTION,
    }:
        raise ValueError("Correction transaction type is unsupported.")
    validate_structured_model_links(model)
    created_at_utc = utc_now_iso()
    transaction_id = transaction_id or _transaction_id(
        operation_id,
        operation_type,
    )
    session_id = (
        str(record.get("session_id") or "").strip()
        if completion_payload is not None
        else ""
    )
    message_id = (
        f"msg.{transaction_id}"
        if completion_payload is not None and session_id
        else None
    )
    session_record = (
        session_record_path(session_id, sessions_dir=sessions_dir)
        if session_id
        else None
    )

    with ExitStack() as locks:
        locks.enter_context(run_lock(run_dir))
        if session_record is not None:
            locks.enter_context(session_lock(session_record))

        latest_record = read_canonical_run_record(
            Path(run_dir) / RUN_RECORD_FILENAME,
            runs_dir=Path(run_dir).parent,
        )
        if latest_record["job_id"] != job_id:
            raise RuntimeError("Correction transaction run identity changed.")
        result_path = Path(run_dir) / "result.json"
        result_payload = read_result_record(run_dir) if result_path.is_file() else {}
        working_model = structured_model_to_working_model(model)
        plantuml = render_structured_model_to_plantuml(model)
        result_payload.update(
            {
                "structured_model": model.model_dump(mode="json"),
                "working_model": working_model.model_dump(mode="json"),
                "plantuml": plantuml,
                "plantuml_url": "",
            }
        )
        result_payload = prepare_result_record_payload(result_payload)
        patches = decision_patches_for_transaction(
            run_dir,
            latest_record,
            result_payload=result_payload,
            model=model,
            name_policy=name_policy,
        )
        patches = sorted_decision_patches(
            merge_decision_patches(patches, name_policy=name_policy)
        )
        decision_projection = {
            "decision_patches": patches,
            "updated_at_utc": created_at_utc,
        }

        artifact_targets: list[PostRunTargetPayload] = []
        target_hashes: dict[str, str] = {}
        for destination, value in result_derived_artifact_values(
            result_payload
        ).items():
            payload = _artifact_bytes(value)
            target_hashes[destination] = post_run_payload_sha256(payload)
            artifact_targets.append(
                PostRunTargetPayload(
                    phase="artifact",
                    scope="run",
                    destination=destination,
                    payload=payload,
                )
            )
        decision_projection_bytes = post_run_json_bytes(decision_projection)
        target_hashes[RUN_DECISION_PATCHES_FILENAME] = post_run_payload_sha256(
            decision_projection_bytes
        )
        result_payload[POST_RUN_RESULT_TRANSACTION_FIELD] = {
            "transaction_id": transaction_id,
            "operation_id": operation_id,
            "operation_type": operation_type,
            "target_hashes": target_hashes,
        }
        result_payload = prepare_result_record_payload(result_payload)

        projected_record = dict(latest_record)
        projected_record["result"] = summarize_run_record(
            {**projected_record, "result": result_payload}
        )
        projected_record["decision_patches_updated_at_utc"] = created_at_utc
        projected_record = validate_canonical_run_record(projected_record)

        targets = [
            *artifact_targets,
            PostRunTargetPayload(
                phase="result",
                scope="run",
                destination="result.json",
                payload=post_run_json_bytes(result_payload),
            ),
            PostRunTargetPayload(
                phase="run_projection",
                scope="run",
                destination=RUN_DECISION_PATCHES_FILENAME,
                payload=decision_projection_bytes,
            ),
            PostRunTargetPayload(
                phase="run_projection",
                scope="run",
                destination=RUN_RECORD_FILENAME,
                payload=post_run_json_bytes(projected_record),
            ),
        ]

        completed_payload = (
            {**completion_payload, "decision_patches": patches}
            if completion_payload is not None
            else None
        )
        if session_record is not None and message_id and completed_payload:
            targets.append(
                PostRunTargetPayload(
                    phase="session",
                    scope="session",
                    destination=SESSION_RECORD_FILENAME,
                    payload=_session_target(
                        session_id=session_id,
                        sessions_dir=sessions_dir,
                        transaction_id=transaction_id,
                        run_id=job_id,
                        message_id=message_id,
                        content=str(completed_payload["summary"]),
                        created_at_utc=created_at_utc,
                    ),
                )
            )

        snapshot_payload = _snapshot_payload(
            model=model,
            results=results,
            summary=summary,
            language_repair=language_repair,
            created_at_utc=created_at_utc,
        )
        trace_events: list[PostRunTraceEventPayload] = []
        if include_snapshot_event:
            trace_events.append(
                PostRunTraceEventPayload(
                    event="partial_model_snapshot",
                    payload=snapshot_payload,
                )
            )
        if completed_payload is not None:
            trace_events.append(
                PostRunTraceEventPayload(
                    event="correction_patch_chat_done",
                    payload=completed_payload,
                )
            )

        transaction_result: PostRunTransactionResult = (
            execute_post_run_transaction(
                run_dir=run_dir,
                sessions_dir=sessions_dir,
                transaction_id=transaction_id,
                operation_id=operation_id,
                operation_type=operation_type,
                created_at_utc=created_at_utc,
                targets=targets,
                trace_events=trace_events,
                session_id=session_id or None,
                chat_message_id=message_id,
            )
        )

    record.clear()
    record.update(projected_record)
    return CorrectionTransactionCommit(
        transaction_id=transaction_result.transaction_id,
        snapshot_payload=snapshot_payload,
        decision_patches=patches,
        completion_payload=completed_payload,
        result_payload=result_payload,
        run_record=projected_record,
        trace_records=transaction_result.trace_records,
    )


__all__ = [
    "CORRECTION_CHECKPOINT_TRANSACTION",
    "CORRECTION_COMPLETION_TRANSACTION",
    "CorrectionTransactionCommit",
    "commit_correction_model_transaction",
]
