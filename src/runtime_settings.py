"""
Runtime settings store.

These settings are meant to be modified while the bot is running and persist across restarts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_RUNTIME_SETTINGS_PATH = "data/runtime_settings.json"


def load_runtime_settings(path: str = DEFAULT_RUNTIME_SETTINGS_PATH) -> Dict[str, Any]:
    settings_path = Path(path)
    if not settings_path.exists():
        return {}

    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        return {}

    return {}


def save_runtime_settings(data: Dict[str, Any], path: str = DEFAULT_RUNTIME_SETTINGS_PATH) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
