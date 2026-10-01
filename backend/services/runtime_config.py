from __future__ import annotations

from backend.api.settings import PROVIDER_LABEL
from core.providers.factory import provider_descriptor


def provider_label(provider: str | None = None) -> str:
    if provider:
        try:
            return provider_descriptor(provider).label
        except ValueError:
            return str(provider)
    return PROVIDER_LABEL


__all__ = ["provider_label"]
