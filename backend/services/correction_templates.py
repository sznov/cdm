from __future__ import annotations

import json
from typing import Any

from backend.services.correction_template_catalog import (
    CORRECTION_TEMPLATES,
    SINGLE_CONSERVATIVE_CORRECTION_MESSAGE,
    SINGLE_CONSERVATIVE_CORRECTION_TEMPLATE_ID,
)


def correction_template_by_id(template_id: str) -> dict[str, Any] | None:
    for template in CORRECTION_TEMPLATES:
        if template.get("id") == template_id:
            return json.loads(json.dumps(template, ensure_ascii=False))
    return None


__all__ = [
    "CORRECTION_TEMPLATES",
    "SINGLE_CONSERVATIVE_CORRECTION_MESSAGE",
    "SINGLE_CONSERVATIVE_CORRECTION_TEMPLATE_ID",
    "correction_template_by_id",
]
