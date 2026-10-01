from __future__ import annotations

import os
from pathlib import Path


def load_dotenv_file(path: Path | None = None) -> dict[str, str]:
    env_path = path or (Path(__file__).resolve().parents[1] / ".env")
    loaded: dict[str, str] = {}
    if not env_path.exists():
        return loaded

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


__all__ = ["load_dotenv_file"]
