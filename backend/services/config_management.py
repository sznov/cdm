from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from harnesses import (
    available_deterministic_functions,
    available_tools,
    get_harness_template,
    list_harness_templates,
)
from core.providers.factory import provider_descriptors_payload

from backend.api.settings import (
    DEFAULT_CORRECTION_TEMPLATE_ID,
    DEFAULT_MODEL,
    DEFAULT_RUNTIME_HARNESS_ID,
    PROVIDER_ID,
)
from backend.services.correction_templates import CORRECTION_TEMPLATES
from backend.services.provider_model_refresh import ProviderCatalogCoordinator
from backend.persistence.startup_recovery import empty_recovery_summary


def app_config_payload(
    provider_catalogs: ProviderCatalogCoordinator,
    *,
    startup_recovery: dict[str, Any] | None = None,
) -> dict[str, Any]:
    providers = provider_descriptors_payload()
    gemini_model_ids: list[str] = []
    if "gemini" in providers:
        gemini_payload = provider_catalogs.catalog_payload("gemini")
        gemini_catalog = {
            key: value for key, value in gemini_payload.items() if key != "state"
        }
        providers["gemini"]["models"] = gemini_catalog["models"]
        providers["gemini"]["model_catalog"] = gemini_catalog
        providers["gemini"]["model_refresh"] = gemini_payload["state"]
        gemini_model_ids = [model["id"] for model in gemini_catalog["models"]]
    providers.pop("codex", None)
    if "nvidia_nim" in providers:
        nvidia_payload = provider_catalogs.catalog_payload("nvidia_nim")
        nvidia_catalog = {
            key: value for key, value in nvidia_payload.items() if key != "state"
        }
        nvidia_refresh = nvidia_payload["state"]
        providers["nvidia_nim"]["models"] = nvidia_catalog["models"]
        providers["nvidia_nim"]["model_catalog"] = nvidia_catalog
        providers["nvidia_nim"]["model_refresh"] = nvidia_refresh
        providers["nvidia_nim"]["catalog_refresh"] = dict(nvidia_refresh)
    return {
        "provider": PROVIDER_ID,
        "default_provider": PROVIDER_ID,
        "providers": providers,
        "default_model": DEFAULT_MODEL,
        "default_runtime_harness_id": DEFAULT_RUNTIME_HARNESS_ID,
        "default_correction_template_id": DEFAULT_CORRECTION_TEMPLATE_ID,
        "gemini_models": gemini_model_ids,
        "startup_recovery": json.loads(
            json.dumps(startup_recovery or empty_recovery_summary(), ensure_ascii=False)
        ),
        "max_iterations": 1000,
        "batch_retries": 10,
        "no_progress_iterations": 2,
        "num_predict": 32768,
        "think": False,
        "language_repair": False,
        "semantic_critic": True,
        "completion_check": True,
        "infer_implicit_identifiers": True,
    }


def correction_templates_payload() -> dict[str, Any]:
    return {
        "default_template_id": DEFAULT_CORRECTION_TEMPLATE_ID,
        "templates": json.loads(json.dumps(CORRECTION_TEMPLATES, ensure_ascii=False)),
    }


def harnesses_payload() -> dict[str, Any]:
    return {
        "harnesses": list_harness_templates(),
        "available_tools": available_tools(),
        "available_deterministic_functions": available_deterministic_functions(),
    }


def harness_payload(harness_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", harness_id):
        raise HTTPException(status_code=400, detail="Invalid harness id.")
    template = get_harness_template(harness_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Harness not found.")
    return {
        "harness": template,
        "available_tools": available_tools(),
        "available_deterministic_functions": available_deterministic_functions(),
    }


__all__ = [
    "app_config_payload",
    "correction_templates_payload",
    "harness_payload",
    "harnesses_payload",
]
