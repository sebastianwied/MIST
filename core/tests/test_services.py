"""Tests for mist_core.broker.services."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mist_core.db import Database
from mist_core.paths import Paths
from mist_core.protocol import Message, MSG_SERVICE_REQUEST, MSG_SERVICE_RESPONSE, MSG_SERVICE_ERROR
from mist_core.storage.settings import Settings
from mist_core.transport import Connection

from mist_core.broker.services import ServiceDispatcher


@pytest.fixture
def paths(tmp_path):
    return Paths(root=tmp_path / "data")


@pytest.fixture
def db(paths):
    database = Database(paths.db)
    database.connect()
    database.init_schema()
    yield database
    database.close()


@pytest.fixture
def settings(paths):
    return Settings(paths)


@pytest.fixture
def dispatcher(paths, db, settings):
    return ServiceDispatcher(paths, db, settings)


@pytest.fixture
def mock_conn():
    conn = MagicMock(spec=Connection)
    conn.send = AsyncMock()
    return conn


def _service_msg(service: str, action: str, params: dict | None = None) -> Message:
    return Message.create(
        MSG_SERVICE_REQUEST, "test-agent", "broker",
        {"service": service, "action": action, "params": params or {}},
    )


def _get_reply(mock_conn) -> Message:
    assert mock_conn.send.called
    return mock_conn.send.call_args[0][0]


# ── Tasks ────────────────────────────────────────────────────────────


class TestTasks:
    async def test_create_and_list(self, dispatcher, mock_conn):
        msg = _service_msg("tasks", "create", {"title": "Buy milk"})
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_RESPONSE
        assert isinstance(reply.payload["result"]["task_id"], int)

        mock_conn.send.reset_mock()
        msg = _service_msg("tasks", "list")
        await dispatcher.handle(msg, mock_conn)
        tasks = _get_reply(mock_conn).payload["result"]
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Buy milk"

    async def test_unknown_action(self, dispatcher, mock_conn):
        msg = _service_msg("tasks", "bogus")
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).type == MSG_SERVICE_ERROR


# ── Events ───────────────────────────────────────────────────────────


class TestEvents:
    async def test_create_and_list(self, dispatcher, mock_conn):
        msg = _service_msg("events", "create", {
            "title": "Meeting", "start_time": "2025-06-01T10:00",
        })
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_RESPONSE
        assert isinstance(reply.payload["result"]["event_id"], int)

        mock_conn.send.reset_mock()
        msg = _service_msg("events", "list")
        await dispatcher.handle(msg, mock_conn)
        events = _get_reply(mock_conn).payload["result"]
        assert len(events) == 1


# ── Articles ─────────────────────────────────────────────────────────


class TestArticles:
    async def test_create_and_list(self, dispatcher, mock_conn):
        msg = _service_msg("articles", "create", {
            "title": "Paper", "authors": ["Author"],
        })
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_RESPONSE

        mock_conn.send.reset_mock()
        msg = _service_msg("articles", "list")
        await dispatcher.handle(msg, mock_conn)
        articles = _get_reply(mock_conn).payload["result"]
        assert len(articles) == 1


# ── Storage (namespaced) ─────────────────────────────────────────────


class TestStorage:
    async def test_save_and_parse_buffer(self, dispatcher, mock_conn):
        msg = _service_msg("storage", "save_raw_input", {"text": "hello", "source": "test"})
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).payload["result"] is True

        mock_conn.send.reset_mock()
        msg = _service_msg("storage", "parse_buffer")
        await dispatcher.handle(msg, mock_conn)
        entries = _get_reply(mock_conn).payload["result"]
        assert len(entries) == 1
        assert entries[0]["text"] == "hello"

    async def test_topic_round_trip(self, dispatcher, mock_conn):
        msg = _service_msg("storage", "add_topic", {"name": "ML", "slug": "ml"})
        await dispatcher.handle(msg, mock_conn)
        topic = _get_reply(mock_conn).payload["result"]
        assert topic["name"] == "ML"

        mock_conn.send.reset_mock()
        msg = _service_msg("storage", "load_topic_index")
        await dispatcher.handle(msg, mock_conn)
        index = _get_reply(mock_conn).payload["result"]
        assert len(index) == 1

    async def test_aggregate_time(self, dispatcher, mock_conn):
        msg = _service_msg("storage", "get_last_aggregate_time")
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).payload["result"] is None

        mock_conn.send.reset_mock()
        msg = _service_msg("storage", "set_last_aggregate_time", {"ts": "2025-01-01T00:00:00"})
        await dispatcher.handle(msg, mock_conn)

        mock_conn.send.reset_mock()
        msg = _service_msg("storage", "get_last_aggregate_time")
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).payload["result"] == "2025-01-01T00:00:00"

    async def test_unknown_action(self, dispatcher, mock_conn):
        msg = _service_msg("storage", "bogus")
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).type == MSG_SERVICE_ERROR


class TestNamespaceIsolation:
    async def test_different_agents_see_own_data(self, dispatcher, mock_conn):
        # Agent A saves a note
        msg_a = Message.create(
            MSG_SERVICE_REQUEST, "agent-a", "broker",
            {"service": "storage", "action": "save_raw_input",
             "params": {"text": "note from A"}},
        )
        await dispatcher.handle(msg_a, mock_conn)

        # Agent B saves a note
        mock_conn.send.reset_mock()
        msg_b = Message.create(
            MSG_SERVICE_REQUEST, "agent-b", "broker",
            {"service": "storage", "action": "save_raw_input",
             "params": {"text": "note from B"}},
        )
        await dispatcher.handle(msg_b, mock_conn)

        # Agent A reads its buffer
        mock_conn.send.reset_mock()
        msg_a2 = Message.create(
            MSG_SERVICE_REQUEST, "agent-a", "broker",
            {"service": "storage", "action": "parse_buffer", "params": {}},
        )
        await dispatcher.handle(msg_a2, mock_conn)
        entries_a = _get_reply(mock_conn).payload["result"]
        assert len(entries_a) == 1
        assert entries_a[0]["text"] == "note from A"

        # Agent B reads its buffer
        mock_conn.send.reset_mock()
        msg_b2 = Message.create(
            MSG_SERVICE_REQUEST, "agent-b", "broker",
            {"service": "storage", "action": "parse_buffer", "params": {}},
        )
        await dispatcher.handle(msg_b2, mock_conn)
        entries_b = _get_reply(mock_conn).payload["result"]
        assert len(entries_b) == 1
        assert entries_b[0]["text"] == "note from B"


# ── Settings ─────────────────────────────────────────────────────────


class TestSettings:
    async def test_get_set(self, dispatcher, mock_conn):
        msg = _service_msg("settings", "set", {"key": "model", "value": "llama3"})
        await dispatcher.handle(msg, mock_conn)

        mock_conn.send.reset_mock()
        msg = _service_msg("settings", "get", {"key": "model"})
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).payload["result"] == "llama3"

    async def test_load_all(self, dispatcher, mock_conn):
        msg = _service_msg("settings", "load_all")
        await dispatcher.handle(msg, mock_conn)
        result = _get_reply(mock_conn).payload["result"]
        assert "agency_mode" in result

    async def test_get_model(self, dispatcher, mock_conn):
        msg = _service_msg("settings", "get_model")
        await dispatcher.handle(msg, mock_conn)
        result = _get_reply(mock_conn).payload["result"]
        assert isinstance(result, str)


# ── Unknown service ──────────────────────────────────────────────────


class TestUnknownService:
    async def test_unknown_service(self, dispatcher, mock_conn):
        msg = _service_msg("bogus_service", "list")
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).type == MSG_SERVICE_ERROR
