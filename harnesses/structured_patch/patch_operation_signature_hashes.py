from __future__ import annotations

import hashlib
import json
from typing import Any

from harnesses.structured_patch.name_policy import (
    LEGACY_ASCII_NAME_POLICY,
    StructuredNamePolicy,
)
from harnesses.structured_patch.patch_operation_signature_payloads import (
    normalized_operation_signature_payload,
)


def _identity_payload(value: Any, name_policy: StructuredNamePolicy) -> Any:
    if isinstance(value, dict):
        return {
            key: _identity_payload(item, name_policy)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_identity_payload(item, name_policy) for item in value]
    if isinstance(value, str):
        return name_policy.comparison_key(value)
    return value


def normalized_operation_signature(
    operation: dict[str, Any] | None,
    *,
    name_policy: StructuredNamePolicy = LEGACY_ASCII_NAME_POLICY,
) -> str | None:
    payload = normalized_operation_signature_payload(operation, name_policy=name_policy)
    if payload is None:
        return None
    identity_payload = _identity_payload(payload, name_policy)
    return hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


__all__ = ["normalized_operation_signature"]
