from __future__ import annotations

import secrets
from contextlib import ExitStack
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
from backend.services.decision_patch_application_context import (
    DecisionPatchApplicationContext,
)
from backend.services.decision_patches import (
    decision_selection_chat_message,
    merge_decision_patches,
    sorted_decision_patches,
)
from core.plantuml_structured import render_structured_model_to_plantuml
from core.schemas import StructuredModel, validate_structured_model_links
from harnesses.structured_patch.model_conversion import (
    structured_model_to_working_model,
)


DECISION_APPLICATION_TRANSACTION = "decision_application"


def _artifact_bytes(value: dict[str, Any] | list[Any] | str) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    return post_run_json_bytes(value)


def _transaction_session_target(
    *,
    context: DecisionPatchApplicationContext,
    transaction_id: str,
    message_id: str,
    chat_content: str,
    created_at_utc: str,
) -> bytes:
    session_id = str(context.record.get("session_id") or "").strip()
    path = session_record_path(
        session_id,
        sessions_dir=context.sessions_dir,
    )
    record = read_canonical_session_record(
        path,
        sessions_dir=context.sessions_dir,
    )
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
            and message.get("post_run_run_id") == context.job_id
            and message.get("content") == chat_content
        ):
            return post_run_json_bytes(record)
        raise RuntimeError("Decision transaction chat identity is occupied.")
    messages.append(
        {
            "id": message_id,
            "role": "user",
            "kind": "decision",
            "content": chat_content,
            "created_at_utc": created_at_utc,
            "post_run_transaction_id": transaction_id,
            "post_run_run_id": context.job_id,
        }
    )
    record["chat_messages"] = messages
    record["updated_at_utc"] = created_at_utc
    return post_run_json_bytes(validate_canonical_session_record(record))


def commit_decision_patch_application(
    context: DecisionPatchApplicationContext,
    *,
    operation_id: str,
    model: StructuredModel,
    results: list[dict[str, Any]],
    applied_events: list[dict[str, Any]],
    chat_selections: list[dict[str, Any]],
    accepted_count: int,
    noted_count: int,
    rejected_count: int,
    changed_count: int,
    transaction_id: str | None = None,
) -> dict[str, Any]:
    """Commit a complete decision batch through the roll-forward protocol."""

    validate_structured_model_links(model)
    created_at_utc = utc_now_iso()
    transaction_id = transaction_id or (
        f"{operation_id}.{DECISION_APPLICATION_TRANSACTION}."
        f"{secrets.token_hex(8)}"
    )
    session_id = str(context.record.get("session_id") or "").strip()
    message_id = f"msg.{transaction_id}" if session_id else None
    session_record = (
        session_record_path(
            session_id,
            sessions_dir=context.sessions_dir,
        )
        if session_id
        else None
    )

    with ExitStack() as locks:
        locks.enter_context(run_lock(context.run_dir))
        if session_record is not None:
            locks.enter_context(session_lock(session_record))

        latest_record = read_canonical_run_record(
            context.record_path,
            runs_dir=context.run_dir.parent,
        )
        working_model = structured_model_to_working_model(model)
        structured_snapshot = model.model_dump(mode="json")
        working_snapshot = working_model.model_dump(mode="json")
        plantuml = render_structured_model_to_plantuml(model)
        result_path = context.run_dir / "result.json"
        result_payload = (
            read_result_record(context.run_dir)
            if result_path.is_file()
            else {}
        )
        patches = sorted_decision_patches(
            merge_decision_patches(
                context.patches,
                name_policy=context.patch_policy.name_policy,
            )
        )
        result_payload.update(
            {
                "structured_model": structured_snapshot,
                "working_model": working_snapshot,
                "plantuml": plantuml,
                "plantuml_url": "",
                "decision_patches": patches,
            }
        )
        result_payload = prepare_result_record_payload(result_payload)
        decision_projection = {
            "decision_patches": patches,
            "updated_at_utc": created_at_utc,
        }
        decision_projection_bytes = post_run_json_bytes(
            decision_projection
        )

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
        target_hashes[RUN_DECISION_PATCHES_FILENAME] = (
            post_run_payload_sha256(decision_projection_bytes)
        )
        result_payload[POST_RUN_RESULT_TRANSACTION_FIELD] = {
            "transaction_id": transaction_id,
            "operation_id": operation_id,
            "operation_type": DECISION_APPLICATION_TRANSACTION,
            "target_hashes": target_hashes,
        }
        result_payload = prepare_result_record_payload(result_payload)

        projected_record = dict(latest_record)
        projected_record["result"] = summarize_run_record(
            {**projected_record, "result": result_payload}
        )
        projected_record["decision_patches_updated_at_utc"] = (
            created_at_utc
        )
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

        chat_content = decision_selection_chat_message(chat_selections)
        if session_record is not None and message_id:
            targets.append(
                PostRunTargetPayload(
                    phase="session",
                    scope="session",
                    destination=SESSION_RECORD_FILENAME,
                    payload=_transaction_session_target(
                        context=context,
                        transaction_id=transaction_id,
                        message_id=message_id,
                        chat_content=chat_content,
                        created_at_utc=created_at_utc,
                    ),
                )
            )

        snapshot_payload = {
            "agent_id": "asyncPlantumlRenderer",
            "diagram_version": int(
                datetime.fromisoformat(
                    created_at_utc.replace("Z", "+00:00")
                ).timestamp()
            ),
            "summary": (
                f"Rendered after {accepted_count} accepted decision patch(es)."
                if changed_count
                else "Decision selection recorded without model changes."
            ),
            "structured_model": structured_snapshot,
            "model_snapshot": working_snapshot,
            "plantuml": plantuml,
            "plantuml_url": "",
            "decision_patch_results": results,
        }
        done_payload = {
            "job_id": context.job_id,
            "accepted_count": accepted_count,
            "noted_count": noted_count,
            "rejected_count": rejected_count,
            "decision_patches": patches,
            "chat_message": {
                "role": "user",
                "kind": "decision",
                "content": chat_content,
            },
            "summary": (
                f"Decision batch complete: {accepted_count} "
                "accepted/already satisfied, "
                f"{noted_count} noted, {rejected_count} rejected."
            ),
        }
        trace_events = [
            PostRunTraceEventPayload(
                event="decision_patch_applied",
                payload=payload,
            )
            for payload in applied_events
        ]
        if changed_count:
            trace_events.append(
                PostRunTraceEventPayload(
                    event="partial_model_snapshot",
                    payload=snapshot_payload,
                )
            )
        trace_events.append(
            PostRunTraceEventPayload(
                event="decision_patch_batch_done",
                payload=done_payload,
            )
        )

        transaction_result = execute_post_run_transaction(
            run_dir=context.run_dir,
            sessions_dir=context.sessions_dir,
            transaction_id=transaction_id,
            operation_id=operation_id,
            operation_type=DECISION_APPLICATION_TRANSACTION,
            created_at_utc=created_at_utc,
            targets=targets,
            trace_events=trace_events,
            session_id=session_id or None,
            chat_message_id=message_id,
        )

    context.record.clear()
    context.record.update(projected_record)
    context.patches[:] = patches
    context.event_sequences.extend(
        int(record["sequence"])
        for record in transaction_result.trace_records
    )
    first_sequence = (
        context.event_sequences[0] if context.event_sequences else None
    )
    last_sequence = (
        context.event_sequences[-1] if context.event_sequences else None
    )
    return {
        "job_id": context.job_id,
        "accepted_count": accepted_count,
        "noted_count": noted_count,
        "rejected_count": rejected_count,
        "results": results,
        "decision_patches": patches,
        "chat_message": done_payload["chat_message"],
        "first_sequence": first_sequence,
        "last_sequence": last_sequence,
        "event_count": len(context.event_sequences),
        **snapshot_payload,
    }


__all__ = [
    "DECISION_APPLICATION_TRANSACTION",
    "commit_decision_patch_application",
]
