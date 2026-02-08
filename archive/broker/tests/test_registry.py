"""Tests for AgentRegistry."""

from unittest.mock import MagicMock

from mist_core.transport import Connection

from mist_broker.registry import AgentRegistry


def _mock_conn():
    return MagicMock(spec=Connection)


class TestRegister:
    def test_assigns_id(self):
        reg = AgentRegistry()
        conn = _mock_conn()
        entry = reg.register(conn, {"name": "mist", "commands": []})
        assert entry.agent_id == "mist-0"
        assert entry.name == "mist"
        assert entry.conn is conn

    def test_unique_ids_same_name(self):
        reg = AgentRegistry()
        e0 = reg.register(_mock_conn(), {"name": "mist", "commands": []})
        e1 = reg.register(_mock_conn(), {"name": "mist", "commands": []})
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
        assert reg.get_by_id("mist-0") is None

    def test_unregister_missing_id(self):
        reg = AgentRegistry()
        assert reg.unregister("nope") is None

    def test_unregister_missing_conn(self):
        reg = AgentRegistry()
        assert reg.unregister_by_conn(_mock_conn()) is None


class TestLookup:
    def test_get_by_id_hit(self):
        reg = AgentRegistry()
        entry = reg.register(_mock_conn(), {"name": "mist"})
        assert reg.get_by_id("mist-0") is entry

    def test_get_by_id_miss(self):
        reg = AgentRegistry()
        assert reg.get_by_id("nope") is None

    def test_get_by_conn_hit(self):
        reg = AgentRegistry()
        conn = _mock_conn()
        entry = reg.register(conn, {"name": "mist"})
        assert reg.get_by_conn(conn) is entry

    def test_get_by_conn_miss(self):
        reg = AgentRegistry()
        assert reg.get_by_conn(_mock_conn()) is None

    def test_all_agents(self):
        reg = AgentRegistry()
        reg.register(_mock_conn(), {"name": "a"})
        reg.register(_mock_conn(), {"name": "b"})
        agents = reg.all_agents()
        assert len(agents) == 2
        ids = {a.agent_id for a in agents}
        assert ids == {"a-0", "b-0"}


class TestCatalog:
    def test_build_catalog(self):
        reg = AgentRegistry()
        reg.register(_mock_conn(), {
            "name": "mist",
            "commands": ["/reflect", "/sync"],
            "description": "Main agent",
        })
        reg.register(_mock_conn(), {"name": "tools", "commands": []})
        catalog = reg.build_catalog()
        assert len(catalog) == 2
        assert catalog[0]["agent_id"] == "mist-0"
        assert catalog[0]["commands"] == ["/reflect", "/sync"]
        assert catalog[0]["description"] == "Main agent"
        assert catalog[1]["agent_id"] == "tools-0"
        assert catalog[1]["commands"] == []
        assert catalog[1]["description"] == ""
