"""Tests for ServiceDispatcher."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from mist_core.protocol import Message, MSG_SERVICE_REQUEST, MSG_SERVICE_RESPONSE, MSG_SERVICE_ERROR
from mist_core.transport import Connection

from mist_broker.services import ServiceDispatcher


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Redirect all core data paths to a temp directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    import mist_core.db as db_mod
    import mist_core.storage as storage_mod
    import mist_core.settings as settings_mod

    monkeypatch.setattr(db_mod, "DB_PATH", data_dir / "mist.db")
    monkeypatch.setattr(storage_mod, "RAWLOG_PATH", data_dir / "notes" / "rawLog.jsonl")
    monkeypatch.setattr(storage_mod, "ARCHIVE_PATH", data_dir / "notes" / "archive.jsonl")
    monkeypatch.setattr(storage_mod, "TOPICS_DIR", data_dir / "topics")
    monkeypatch.setattr(storage_mod, "TOPIC_INDEX_PATH", data_dir / "topics" / "index.json")
    monkeypatch.setattr(storage_mod, "SYNTHESIS_DIR", data_dir / "synthesis")
    monkeypatch.setattr(storage_mod, "CONTEXT_PATH", data_dir / "synthesis" / "context.md")
    monkeypatch.setattr(storage_mod, "LAST_AGGREGATE_PATH", data_dir / "state" / "last_aggregate.txt")
    monkeypatch.setattr(storage_mod, "LAST_SYNC_PATH", data_dir / "state" / "last_sync.txt")
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", data_dir / "config" / "settings.json")
    monkeypatch.setattr(settings_mod, "MODEL_PATH", data_dir / "config" / "model.conf")

    return data_dir


@pytest.fixture
def dispatcher(tmp_data):
    d = ServiceDispatcher()
    d.initialize()
    return d


@pytest.fixture
def mock_conn():
    conn = MagicMock(spec=Connection)
    conn.send = AsyncMock()
    return conn


def _service_msg(service: str, action: str, params: dict | None = None) -> Message:
    return Message.create(
        MSG_SERVICE_REQUEST, "test", "broker",
        {"service": service, "action": action, "params": params or {}},
    )


def _get_reply(mock_conn) -> Message:
    """Extract the Message passed to the last conn.send() call."""
    assert mock_conn.send.called
    return mock_conn.send.call_args[0][0]


# ── Tasks ────────────────────────────────────────────────────────────


class TestTasks:
    async def test_create_and_list(self, dispatcher, mock_conn):
        # Create
        msg = _service_msg("tasks", "create", {"title": "Buy milk"})
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_RESPONSE
        task_id = reply.payload["result"]["task_id"]
        assert isinstance(task_id, int)

        # List
        mock_conn.send.reset_mock()
        msg = _service_msg("tasks", "list")
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        tasks = reply.payload["result"]
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Buy milk"

    async def test_get(self, dispatcher, mock_conn):
        msg = _service_msg("tasks", "create", {"title": "Test"})
        await dispatcher.handle(msg, mock_conn)
        tid = _get_reply(mock_conn).payload["result"]["task_id"]

        mock_conn.send.reset_mock()
        msg = _service_msg("tasks", "get", {"task_id": tid})
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.payload["result"]["title"] == "Test"

    async def test_update(self, dispatcher, mock_conn):
        msg = _service_msg("tasks", "create", {"title": "Old"})
        await dispatcher.handle(msg, mock_conn)
        tid = _get_reply(mock_conn).payload["result"]["task_id"]

        mock_conn.send.reset_mock()
        msg = _service_msg("tasks", "update", {"task_id": tid, "title": "New"})
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.payload["result"] is True

    async def test_delete(self, dispatcher, mock_conn):
        msg = _service_msg("tasks", "create", {"title": "Del"})
        await dispatcher.handle(msg, mock_conn)
        tid = _get_reply(mock_conn).payload["result"]["task_id"]

        mock_conn.send.reset_mock()
        msg = _service_msg("tasks", "delete", {"task_id": tid})
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.payload["result"] is True

    async def test_upcoming(self, dispatcher, mock_conn):
        msg = _service_msg("tasks", "upcoming")
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_RESPONSE
        assert isinstance(reply.payload["result"], list)

    async def test_unknown_action(self, dispatcher, mock_conn):
        msg = _service_msg("tasks", "bogus")
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_ERROR
        assert "unknown tasks action" in reply.payload["error"]


# ── Events ───────────────────────────────────────────────────────────


class TestEvents:
    async def test_create_and_list(self, dispatcher, mock_conn):
        msg = _service_msg("events", "create", {
            "title": "Meeting",
            "start_time": "2025-06-01T10:00:00",
        })
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_RESPONSE
        eid = reply.payload["result"]["event_id"]
        assert isinstance(eid, int)

        mock_conn.send.reset_mock()
        msg = _service_msg("events", "list")
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        events = reply.payload["result"]
        assert len(events) == 1
        assert events[0]["title"] == "Meeting"

    async def test_get(self, dispatcher, mock_conn):
        msg = _service_msg("events", "create", {
            "title": "E", "start_time": "2025-06-01T10:00:00",
        })
        await dispatcher.handle(msg, mock_conn)
        eid = _get_reply(mock_conn).payload["result"]["event_id"]

        mock_conn.send.reset_mock()
        msg = _service_msg("events", "get", {"event_id": eid})
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.payload["result"]["title"] == "E"

    async def test_delete(self, dispatcher, mock_conn):
        msg = _service_msg("events", "create", {
            "title": "D", "start_time": "2025-06-01T10:00:00",
        })
        await dispatcher.handle(msg, mock_conn)
        eid = _get_reply(mock_conn).payload["result"]["event_id"]

        mock_conn.send.reset_mock()
        msg = _service_msg("events", "delete", {"event_id": eid})
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.payload["result"] is True

    async def test_unknown_action(self, dispatcher, mock_conn):
        msg = _service_msg("events", "bogus")
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_ERROR


# ── Storage ──────────────────────────────────────────────────────────


class TestStorage:
    async def test_save_and_parse_rawlog(self, dispatcher, mock_conn):
        msg = _service_msg("storage", "save_raw_input", {"text": "hello", "source": "test"})
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).payload["result"] is True

        mock_conn.send.reset_mock()
        msg = _service_msg("storage", "parse_rawlog")
        await dispatcher.handle(msg, mock_conn)
        entries = _get_reply(mock_conn).payload["result"]
        assert len(entries) == 1
        assert entries[0]["text"] == "hello"

    async def test_context_round_trip(self, dispatcher, mock_conn):
        msg = _service_msg("storage", "save_context", {"text": "summary"})
        await dispatcher.handle(msg, mock_conn)

        mock_conn.send.reset_mock()
        msg = _service_msg("storage", "load_context")
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).payload["result"] == "summary"

    async def test_topic_index(self, dispatcher, mock_conn):
        msg = _service_msg("storage", "load_topic_index")
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).payload["result"] == []

    async def test_add_and_find_topic(self, dispatcher, mock_conn):
        msg = _service_msg("storage", "add_topic", {"name": "Work", "slug": "work"})
        await dispatcher.handle(msg, mock_conn)
        topic = _get_reply(mock_conn).payload["result"]
        assert topic["name"] == "Work"
        assert topic["slug"] == "work"

        mock_conn.send.reset_mock()
        msg = _service_msg("storage", "find_topic", {"identifier": "work"})
        await dispatcher.handle(msg, mock_conn)
        found = _get_reply(mock_conn).payload["result"]
        assert found["slug"] == "work"

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


# ── Settings ─────────────────────────────────────────────────────────


class TestSettings:
    async def test_get_set_round_trip(self, dispatcher, mock_conn):
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
        assert isinstance(result, dict)
        assert "agency_mode" in result

    async def test_is_valid_key(self, dispatcher, mock_conn):
        msg = _service_msg("settings", "is_valid_key", {"key": "model"})
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).payload["result"] is True

        mock_conn.send.reset_mock()
        msg = _service_msg("settings", "is_valid_key", {"key": "bogus_key"})
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).payload["result"] is False

    async def test_get_model(self, dispatcher, mock_conn):
        msg = _service_msg("settings", "get_model")
        await dispatcher.handle(msg, mock_conn)
        result = _get_reply(mock_conn).payload["result"]
        assert isinstance(result, str)
        assert len(result) > 0

    async def test_unknown_action(self, dispatcher, mock_conn):
        msg = _service_msg("settings", "bogus")
        await dispatcher.handle(msg, mock_conn)
        assert _get_reply(mock_conn).type == MSG_SERVICE_ERROR


# ── Unknown service ──────────────────────────────────────────────────


class TestUnknownService:
    async def test_unknown_service(self, dispatcher, mock_conn):
        msg = _service_msg("bogus_service", "list")
        await dispatcher.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_ERROR
        assert "unknown service" in reply.payload["error"]
