"""Settings system backed by data/config/settings.json."""

import json
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path("data/config/settings.json")

DEFAULTS: dict[str, Any] = {
    "agency_mode": "suggest",
    "context_tasks_days": 7,
    "context_events_days": 3,
}


def load_settings() -> dict[str, Any]:
    """Read settings from disk, filling missing keys from defaults."""
    settings = dict(DEFAULTS)
    try:
        raw = SETTINGS_PATH.read_text(encoding="utf-8")
        stored = json.loads(raw)
        settings.update(stored)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    """Write settings to disk, creating the file if needed."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(settings, indent=4) + "\n", encoding="utf-8",
    )


def get_setting(key: str) -> Any:
    """Return a single setting value."""
    return load_settings().get(key, DEFAULTS.get(key))


def set_setting(key: str, value: Any) -> None:
    """Update a single setting and persist."""
    settings = load_settings()
    settings[key] = value
    save_settings(settings)
