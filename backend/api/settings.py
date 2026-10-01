from __future__ import annotations

import os
from pathlib import Path

from core.runtime_env import load_dotenv_file


BASE_DIR = Path(__file__).resolve().parents[2]


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return Path(value).expanduser().resolve()


STATIC_DIR = _env_path("CONCEPTUAL_MODEL_GENERATOR_STATIC_DIR", BASE_DIR / "static")
DB_DIR = _env_path("CONCEPTUAL_MODEL_GENERATOR_DATA_DIR", BASE_DIR / "__db__")
RUNS_DIR = DB_DIR / "runs"
SESSIONS_DIR = DB_DIR / "sessions"

load_dotenv_file(BASE_DIR / ".env")

DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemma-4-31b-it")
PROVIDER_ID = "gemini"
PROVIDER_LABEL = "Gemini API"
DEFAULT_RUNTIME_HARNESS_ID = "structured-patch-refined"
DEFAULT_CORRECTION_TEMPLATE_ID = "default-correction-sequence"
STRUCTURED_PATCH_HARNESS_IDS = {
    "gemma4-tuned-final",
    "structured-patch-refined",
}
DIRECT_BASELINE_HARNESS_IDS = {"direct-baseline-schema-only-v1"}

RUN_RECORD_FILENAME = "run.json"
RUN_TRACE_FILENAME = "trace.jsonl"
RUN_SPECIFICATION_FILENAME = "specification.txt"
RUN_DECISION_PATCHES_FILENAME = "decision_patches.json"
SESSION_RECORD_FILENAME = "session.json"
