from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.api.settings import RUN_DECISION_PATCHES_FILENAME
from backend.persistence.common import read_json_file, utc_now_iso, write_json_file
from backend.persistence.locks import run_lock
from backend.persistence.post_run_transaction_guard import (
    require_post_run_mutation_allowed,
)
from backend.persistence.run_sources import structured_model_from_run_dir
from core.schemas import StructuredModel
from harnesses.structured_patch.decision_identifier_context import propose_identifier_context_decision_patches
from harnesses.structured_patch.decision_merge import (
    merge_decision_patches,
    merge_decision_patches_latest_state,
)
from harnesses.structured_patch.name_policy import StructuredNamePolicy
from backend.services.decision_identifier_context import (
    decision_patch_is_identifier_context_addition,
    merge_identifier_context_operation,
)
from backend.services.decision_patch_conflicts import (
    decision_choice_identifier_conflict_key,
    decision_operation_identifier_conflict_key,
    reject_conflicting_identifier_decision_choices,
)
from backend.services.decision_patch_options import (
    decision_option_by_id,
    decision_option_operation,
    decision_patch_is_final,
    decision_patch_requires_choice,
    decision_patch_sort_rank,
    decision_selection_chat_message,
    normalized_decision_patch_options_for_apply,
    sorted_decision_patches,
)
from backend.services.decision_patch_rebase import (
    rebase_decision_operation_for_current_model,
    structured_language_rename_maps_for_run,
    update_decision_patch_operation_references,
)


def decision_patches_from_result_payload(
    result_payload: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy,
) -> list[dict[str, Any]]:
    if not isinstance(result_payload, dict):
        return []
    patches: list[dict[str, Any]] = []
    for check in result_payload.get("completion_checks") or []:
        if isinstance(check, dict) and isinstance(check.get("decision_patches"), list):
            patches.extend(patch for patch in check["decision_patches"] if isinstance(patch, dict))
    current = result_payload.get("decision_patches")
    if isinstance(current, list):
        patches.extend(
            patch for patch in current if isinstance(patch, dict)
        )
    return merge_decision_patches_latest_state(patches, name_policy=name_policy)


def _decision_patches_for_run(
    run_dir: Path,
    record: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy,
    result_payload_override: dict[str, Any] | None = None,
    model_override: Any | None = None,
    persist_reconciliation: bool = True,
) -> list[dict[str, Any]]:
    patch_path = run_dir / RUN_DECISION_PATCHES_FILENAME
    if patch_path.is_file():
        try:
            payload = read_json_file(patch_path)
            patches = payload.get("decision_patches")
            if isinstance(patches, list):
                normalized = sorted_decision_patches(
                    merge_decision_patches(
                        [patch for patch in patches if isinstance(patch, dict)],
                        name_policy=name_policy,
                    )
                )
                if persist_reconciliation and json.dumps(
                    normalized,
                    sort_keys=True,
                    ensure_ascii=False,
                ) != json.dumps(
                    [patch for patch in patches if isinstance(patch, dict)],
                    sort_keys=True,
                    ensure_ascii=False,
                ):
                    write_json_file(patch_path, {"decision_patches": normalized, "updated_at_utc": utc_now_iso()})
                return normalized
        except (OSError, json.JSONDecodeError):
            pass

    result_path = run_dir / "result.json"
    result_payload: dict[str, Any] | None = result_payload_override
    if result_payload is None and result_path.is_file():
        try:
            result_payload = read_json_file(result_path)
        except (OSError, json.JSONDecodeError):
            result_payload = None
    if result_payload is None and isinstance(record.get("result"), dict):
        result_payload = record.get("result")

    patches = decision_patches_from_result_payload(
        result_payload,
        name_policy=name_policy,
    )
    effective_payload = record.get("effective_harness_run_spec")
    effective_config = (
        effective_payload.get("effective_config")
        if isinstance(effective_payload, dict)
        and isinstance(effective_payload.get("effective_config"), dict)
        else {}
    )
    if effective_config.get("infer_implicit_identifiers"):
        model = model_override or structured_model_from_run_dir(run_dir)
        if model is not None:
            patches = merge_decision_patches(
                patches,
                propose_identifier_context_decision_patches(model, name_policy=name_policy),
                name_policy=name_policy,
            )
    patches = sorted_decision_patches(
        merge_decision_patches(patches, name_policy=name_policy)
    )
    if patches and persist_reconciliation:
        write_json_file(patch_path, {"decision_patches": patches, "updated_at_utc": utc_now_iso()})
    return patches


def decision_patches_for_run(
    run_dir: Path,
    record: dict[str, Any],
    *,
    name_policy: StructuredNamePolicy,
) -> list[dict[str, Any]]:
    with run_lock(run_dir):
        require_post_run_mutation_allowed(run_dir)
        return _decision_patches_for_run(
            run_dir,
            record,
            name_policy=name_policy,
        )


def decision_patches_for_transaction(
    run_dir: Path,
    record: dict[str, Any],
    *,
    result_payload: dict[str, Any],
    model: StructuredModel,
    name_policy: StructuredNamePolicy,
) -> list[dict[str, Any]]:
    """Resolve current decision patches without publishing reconciliation."""

    with run_lock(run_dir):
        require_post_run_mutation_allowed(run_dir)
        return _decision_patches_for_run(
            run_dir,
            record,
            name_policy=name_policy,
            result_payload_override=result_payload,
            model_override=model,
            persist_reconciliation=False,
        )


def persist_decision_patches(
    run_dir: Path,
    patches: list[dict[str, Any]],
    *,
    name_policy: StructuredNamePolicy,
) -> None:
    with run_lock(run_dir):
        require_post_run_mutation_allowed(run_dir)
        write_json_file(
            run_dir / RUN_DECISION_PATCHES_FILENAME,
            {
                "decision_patches": sorted_decision_patches(
                    merge_decision_patches(patches, name_policy=name_policy)
                ),
                "updated_at_utc": utc_now_iso(),
            },
        )


__all__ = [
    "decision_choice_identifier_conflict_key",
    "decision_operation_identifier_conflict_key",
    "decision_option_by_id",
    "decision_option_operation",
    "decision_patch_is_final",
    "decision_patch_is_identifier_context_addition",
    "decision_patch_requires_choice",
    "decision_patch_sort_rank",
    "decision_patches_for_run",
    "decision_patches_for_transaction",
    "decision_patches_from_result_payload",
    "decision_selection_chat_message",
    "merge_identifier_context_operation",
    "normalized_decision_patch_options_for_apply",
    "persist_decision_patches",
    "rebase_decision_operation_for_current_model",
    "reject_conflicting_identifier_decision_choices",
    "sorted_decision_patches",
    "structured_language_rename_maps_for_run",
    "update_decision_patch_operation_references",
]
