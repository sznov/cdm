from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CheckpointCorrectionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str
    changed_count: int = Field(default=0, ge=0)
    checkpoint_stage: str = ""


class CheckpointManifestRow(BaseModel):
    """Stable judge-facing checkpoint row with family-specific extensions."""

    model_config = ConfigDict(extra="allow")

    spec_id: str
    generation_run_id: str
    checkpoint_label: str
    spec_path: str | None = None
    reference_model_path: str | None = None
    gold_path: str | None = None
    model_path: str
    plantuml_path: str | None = None
    plantuml_url: str | None = None
    provider: str | None = None
    model: str | None = None
    harness_id: str | None = None
    status: str | None = None
    correction_sequence: CheckpointCorrectionSummary | None = None

    def detached_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_unset=True)


__all__ = ["CheckpointCorrectionSummary", "CheckpointManifestRow"]
