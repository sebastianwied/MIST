"""Tests for mist_core.storage.settings."""

import pytest

from mist_core.paths import Paths
from mist_core.storage.settings import Settings, DEFAULT_MODEL


@pytest.fixture
def paths(tmp_path):
    return Paths(root=tmp_path / "data")


@pytest.fixture
def settings(paths):
    return Settings(paths)


class TestSettings:
    def test_load_defaults(self, settings):
        s = settings.load()
        assert s["agency_mode"] == "suggest"
        assert s["context_tasks_days"] == 7

    def test_save_and_load(self, settings):
        settings.set("agency_mode", "auto")
        assert settings.get("agency_mode") == "auto"

    def test_get_missing_key(self, settings):
        assert settings.get("nonexistent") is None

    def test_valid_keys(self):
        assert Settings.is_valid_key("model")
        assert Settings.is_valid_key("model_reflect")
        assert not Settings.is_valid_key("invalid_key")


class TestModelResolution:
    def test_default_model(self, settings):
        assert settings.get_model() == DEFAULT_MODEL

    def test_global_override(self, settings):
        settings.set("model", "llama3")
        assert settings.get_model() == "llama3"

    def test_per_command_override(self, settings):
        settings.set("model", "llama3")
        settings.set("model_reflect", "gpt4")
        assert settings.get_model("reflect") == "gpt4"
        assert settings.get_model("recall") == "llama3"  # falls back to global

    def test_command_fallback_to_global(self, settings):
        settings.set("model", "llama3")
        assert settings.get_model("aggregate") == "llama3"

    def test_command_fallback_to_default(self, settings):
        assert settings.get_model("reflect") == DEFAULT_MODEL
