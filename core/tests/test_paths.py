"""Tests for mist_core.paths."""

from pathlib import Path

from mist_core.paths import Paths


class TestPaths:
    def test_root(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.root == tmp_path / "data"

    def test_db(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.db == tmp_path / "data" / "mist.db"

    def test_settings_file(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.settings_file == tmp_path / "data" / "config" / "settings.json"

    def test_socket_path(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.socket_path == tmp_path / "data" / "broker" / "mist.sock"


class TestAgentPaths:
    def test_agent_dir(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.agent_dir("notes-0") == tmp_path / "data" / "agents" / "notes-0"

    def test_agent_persona(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.agent_persona("notes-0") == (
            tmp_path / "data" / "agents" / "notes-0" / "config" / "persona.md"
        )

    def test_agent_note_buffer(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.agent_note_buffer("notes-0") == (
            tmp_path / "data" / "agents" / "notes-0" / "notes" / "noteBuffer.jsonl"
        )

    def test_agent_topic_dir(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.agent_topic_dir("notes-0", "ml") == (
            tmp_path / "data" / "agents" / "notes-0" / "topics" / "ml"
        )

    def test_agent_topic_synthesis(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.agent_topic_synthesis("notes-0", "ml") == (
            tmp_path / "data" / "agents" / "notes-0" / "topics" / "ml" / "synthesis.md"
        )

    def test_agent_topic_note_feed(self, tmp_path):
        p = Paths(tmp_path / "data")
        assert p.agent_topic_note_feed("notes-0", "ml") == (
            tmp_path / "data" / "agents" / "notes-0" / "topics" / "ml" / "noteFeed.md"
        )


class TestEnsureAgentDirs:
    def test_creates_directories(self, tmp_path):
        p = Paths(tmp_path / "data")
        p.ensure_agent_dirs("notes-0")
        assert p.agent_config_dir("notes-0").is_dir()
        assert p.agent_notes_dir("notes-0").is_dir()
        assert p.agent_topics_dir("notes-0").is_dir()

    def test_idempotent(self, tmp_path):
        p = Paths(tmp_path / "data")
        p.ensure_agent_dirs("notes-0")
        p.ensure_agent_dirs("notes-0")  # no error

    def test_different_agents_isolated(self, tmp_path):
        p = Paths(tmp_path / "data")
        p.ensure_agent_dirs("notes-0")
        p.ensure_agent_dirs("science-0")
        assert p.agent_dir("notes-0") != p.agent_dir("science-0")
        assert p.agent_dir("notes-0").is_dir()
        assert p.agent_dir("science-0").is_dir()
