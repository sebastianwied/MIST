"""Tests for mist_core.broker.registry."""

from unittest.mock import MagicMock

from mist_core.transport import Connection
from mist_core.broker.registry import AgentRegistry


def _mock_conn():
    return MagicMock(spec=Connection)


class TestRegister:
    def test_assigns_id(self):
        reg = AgentRegistry()
        entry = reg.register(_mock_conn(), {"name": "mist", "commands": []})
        assert entry.agent_id == "mist-0"
        assert entry.name == "mist"

    def test_unique_ids_same_name(self):
        reg = AgentRegistry()
        e0 = reg.register(_mock_conn(), {"name": "mist"})
        e1 = reg.register(_mock_conn(), {"name": "mist"})
        assert e0.agent_id == "mist-0"
        assert e1.agent_id == "mist-1"

    def test_different_names_independent_counters(self):
        reg = AgentRegistry()
        ea = reg.register(_mock_conn(), {"name": "alpha"})
        eb = reg.register(_mock_conn(), {"name": "beta"})
        assert ea.agent_id == "alpha-0"
        assert eb.agent_id == "beta-0"

    def test_default_name(self):
        reg = AgentRegistry()
        entry = reg.register(_mock_conn(), {})
        assert entry.agent_id == "agent-0"

    def test_privileged_flag(self):
        reg = AgentRegistry()
        entry = reg.register(None, {"name": "admin"}, privileged=True)
        assert entry.privileged is True
        assert entry.conn is None

    def test_not_privileged_by_default(self):
        reg = AgentRegistry()
        entry = reg.register(_mock_conn(), {"name": "notes"})
        assert entry.privileged is False


class TestUnregister:
    def test_by_id(self):
        reg = AgentRegistry()
        conn = _mock_conn()
        entry = reg.register(conn, {"name": "mist"})
        removed = reg.unregister("mist-0")
        assert removed is entry
        assert reg.get_by_id("mist-0") is None
        assert reg.get_by_conn(conn) is None

    def test_by_conn(self):
        reg = AgentRegistry()
        conn = _mock_conn()
        entry = reg.register(conn, {"name": "mist"})
        removed = reg.unregister_by_conn(conn)
        assert removed is entry

    def test_unregister_missing(self):
        reg = AgentRegistry()
        assert reg.unregister("nope") is None
        assert reg.unregister_by_conn(_mock_conn()) is None


class TestLookup:
    def test_get_by_id(self):
        reg = AgentRegistry()
        entry = reg.register(_mock_conn(), {"name": "mist"})
        assert reg.get_by_id("mist-0") is entry
        assert reg.get_by_id("nope") is None

    def test_get_by_conn(self):
        reg = AgentRegistry()
        conn = _mock_conn()
        entry = reg.register(conn, {"name": "mist"})
        assert reg.get_by_conn(conn) is entry
        assert reg.get_by_conn(_mock_conn()) is None

    def test_all_agents(self):
        reg = AgentRegistry()
        reg.register(_mock_conn(), {"name": "a"})
        reg.register(_mock_conn(), {"name": "b"})
        assert len(reg.all_agents()) == 2


class TestDefaultAgent:
    def test_returns_privileged(self):
        reg = AgentRegistry()
        reg.register(_mock_conn(), {"name": "notes"})
        admin = reg.register(None, {"name": "admin"}, privileged=True)
        assert reg.get_default_agent() is admin

    def test_returns_none_when_no_privileged(self):
        reg = AgentRegistry()
        reg.register(_mock_conn(), {"name": "notes"})
        assert reg.get_default_agent() is None


class TestFindCommandOwner:
    def test_finds_owner(self):
        reg = AgentRegistry()
        reg.register(_mock_conn(), {
            "name": "notes",
            "commands": [{"name": "note"}, {"name": "recall"}],
        })
        entry = reg.find_command_owner("note")
        assert entry is not None
        assert entry.name == "notes"

    def test_returns_none_for_unknown(self):
        reg = AgentRegistry()
        reg.register(_mock_conn(), {"name": "notes", "commands": []})
        assert reg.find_command_owner("unknown") is None

    def test_string_commands(self):
        reg = AgentRegistry()
        reg.register(_mock_conn(), {"name": "admin", "commands": ["help", "status"]})
        assert reg.find_command_owner("help") is not None


class TestCatalog:
    def test_build_catalog(self):
        reg = AgentRegistry()
        reg.register(_mock_conn(), {
            "name": "mist",
            "commands": [{"name": "note"}],
            "description": "Main agent",
            "panels": [{"id": "chat", "type": "chat"}],
        })
        catalog = reg.build_catalog()
        assert len(catalog) == 1
        assert catalog[0]["agent_id"] == "mist-0"
        assert catalog[0]["description"] == "Main agent"
        assert catalog[0]["panels"] == [{"id": "chat", "type": "chat"}]
