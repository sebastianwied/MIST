"""Settings system backed by data/config/settings.json."""

import json
from pathlib import Path
from typing import Any

SETTINGS_PATH = Path("data/config/settings.json")
MODEL_PATH = Path("data/config/model.conf")
DEFAULT_MODEL = "gemma3:1b"

# Commands that can have per-command model overrides (model_<command>).
MODEL_COMMANDS = (
    "reflect", "recall", "sync", "resynth", "synthesis",
    "aggregate", "extract", "persona", "profile", "review",
)

DEFAULTS: dict[str, Any] = {
    "agency_mode": "suggest",
    "context_tasks_days": 7,
    "context_events_days": 3,
    "model": "",
}

# All recognised setting keys (base defaults + per-command model keys).
_VALID_KEYS = set(DEFAULTS) | {f"model_{cmd}" for cmd in MODEL_COMMANDS}


def _load_model_conf() -> str:
    """Read the model name from model.conf, returning empty string if missing."""
    try:
        return MODEL_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


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


def is_valid_setting_key(key: str) -> bool:
    """Return True if *key* is a recognised setting name."""
    return key in _VALID_KEYS


def get_model(command: str | None = None) -> str:
    """Resolve the model name for *command* using the priority chain:

    settings.model_<command> → settings.model → model.conf → DEFAULT_MODEL
    """
    settings = load_settings()

    # 1. Per-command override
    if command:
        per_cmd = settings.get(f"model_{command}", "")
        if per_cmd:
            return per_cmd

    # 2. Global settings override
    global_model = settings.get("model", "")
    if global_model:
        return global_model

    # 3. Legacy model.conf file
    conf_model = _load_model_conf()
    if conf_model:
        return conf_model

    # 4. Hard-coded default
    return DEFAULT_MODEL
