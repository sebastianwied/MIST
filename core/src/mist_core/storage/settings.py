"""Settings system backed by JSON file, class-based."""

from __future__ import annotations

import json
from typing import Any

from ..paths import Paths

DEFAULT_MODEL = "gemma3:1b"

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

_VALID_KEYS = set(DEFAULTS) | {f"model_{cmd}" for cmd in MODEL_COMMANDS}


class Settings:
    """Settings backed by a JSON file.

    Usage:
        settings = Settings(paths)
        model = settings.get_model("reflect")
        settings.set("model", "llama3")
    """

    def __init__(self, paths: Paths) -> None:
        self.paths = paths

    def load(self) -> dict[str, Any]:
        """Read settings from disk, filling missing keys from defaults."""
        settings = dict(DEFAULTS)
        try:
            raw = self.paths.settings_file.read_text(encoding="utf-8")
            stored = json.loads(raw)
            settings.update(stored)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return settings

    def save(self, settings: dict[str, Any]) -> None:
        """Write settings to disk."""
        self.paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
        self.paths.settings_file.write_text(
            json.dumps(settings, indent=4) + "\n", encoding="utf-8",
        )

    def get(self, key: str) -> Any:
        """Return a single setting value."""
        return self.load().get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        """Update a single setting and persist."""
        settings = self.load()
        settings[key] = value
        self.save(settings)

    @staticmethod
    def is_valid_key(key: str) -> bool:
        """Return True if *key* is a recognised setting name."""
        return key in _VALID_KEYS

    def get_model(self, command: str | None = None) -> str:
        """Resolve the model name using the priority chain:

        settings.model_<command> -> settings.model -> DEFAULT_MODEL
        """
        settings = self.load()

        if command:
            per_cmd = settings.get(f"model_{command}", "")
            if per_cmd:
                return per_cmd

        global_model = settings.get("model", "")
        if global_model:
            return global_model

        return DEFAULT_MODEL
