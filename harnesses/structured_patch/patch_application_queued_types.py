from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.schemas import StructuredModel


@dataclass
class QueuedRemovalApplicationResult:
    model: StructuredModel
    decision_patches: list[dict[str, Any]]


__all__ = ["QueuedRemovalApplicationResult"]
