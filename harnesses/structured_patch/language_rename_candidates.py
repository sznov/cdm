from __future__ import annotations

from typing import Any

from core.naming import to_lower_camel_ascii, to_upper_camel_ascii
from harnesses.structured_patch.language_word_support import repair_name_support


UNSUPPORTED_SPEC_LANGUAGE_RENAME_REASON = (
    "Rename rejected because the proposed name contains words not supported by the specification language."
)


def normalize_language_rename_candidate(rename: dict[str, str], *, kind: str) -> dict[str, str]:
    normalized = dict(rename)
    if kind == "entity":
        normalized["new"] = to_upper_camel_ascii((rename.get("new") or "").strip(), fallback="")
    else:
        normalized["new"] = to_lower_camel_ascii((rename.get("new") or "").strip(), fallback="")
    normalized["kind"] = kind
    normalized["old"] = (rename.get("old") or "").strip()
    normalized["entity"] = (rename.get("entity") or "").strip()
    normalized["reason"] = (rename.get("reason") or "").strip()
    return normalized


def rejected_language_rename_payload(rename: dict[str, str], reason: str, **extra: Any) -> dict[str, Any]:
    return {**rename, "accepted": False, "reason": reason, **extra}


def unsupported_spec_language_rejection(
    rename: dict[str, str],
    *,
    spec_words: set[str],
) -> dict[str, Any] | None:
    support = repair_name_support(rename["new"], spec_words=spec_words)
    if support["supported"]:
        return None
    return rejected_language_rename_payload(
        rename,
        UNSUPPORTED_SPEC_LANGUAGE_RENAME_REASON,
        unsupported_words=support["unsupported_words"],
    )


__all__ = [
    "UNSUPPORTED_SPEC_LANGUAGE_RENAME_REASON",
    "normalize_language_rename_candidate",
    "rejected_language_rename_payload",
    "unsupported_spec_language_rejection",
]
