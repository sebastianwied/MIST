"""Tests for MessageRouter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mist_core.protocol import (
    Message,
    MSG_AGENT_CATALOG,
    MSG_AGENT_DISCONNECT,
    MSG_AGENT_LIST,
    MSG_AGENT_READY,
    MSG_AGENT_REGISTER,
    MSG_COMMAND,
    MSG_ERROR,
    MSG_RESPONSE,
    MSG_RESPONSE_CHUNK,
    MSG_RESPONSE_END,
    MSG_SERVICE_REQUEST,
)
from mist_core.transport import Connection

from mist_broker.registry import AgentRegistry, AgentEntry
from mist_broker.router import MessageRouter
from mist_broker.services import ServiceDispatcher
from mist_broker.llm_service import LLMService


@pytest.fixture
def mock_conn():
    conn = MagicMock(spec=Connection)
    conn.send = AsyncMock()
    return conn


@pytest.fixture
def mock_conn2():
    conn = MagicMock(spec=Connection)
    conn.send = AsyncMock()
    return conn


@pytest.fixture
def registry():
    return AgentRegistry()


@pytest.fixture
def services():
    svc = MagicMock(spec=ServiceDispatcher)
    svc.handle = AsyncMock()
    return svc


@pytest.fixture
def llm():
    l = MagicMock(spec=LLMService)
    l.handle = AsyncMock()
    return l


@pytest.fixture
def router(registry, services, llm):
    return MessageRouter(registry, services, llm)


def _get_reply(conn) -> Message:
    assert conn.send.called
    return conn.send.call_args[0][0]


# ── Registration ─────────────────────────────────────────────────────


class TestRegister:
    async def test_register_sends_ready(self, router, mock_conn, registry):
        msg = Message.create(
            MSG_AGENT_REGISTER, "client", "broker",
            {"name": "mist", "commands": ["/reflect"]},
        )
        await router.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_AGENT_READY
        assert reply.payload["agent_id"] == "mist-0"
        assert reply.reply_to == msg.id
        # Verify registered
        assert registry.get_by_id("mist-0") is not None

    async def test_disconnect_removes_agent(self, router, mock_conn, registry):
        # Register first
        reg_msg = Message.create(
            MSG_AGENT_REGISTER, "client", "broker", {"name": "mist"},
        )
        await router.handle(reg_msg, mock_conn)
        assert registry.get_by_conn(mock_conn) is not None

        # Disconnect
        disc_msg = Message.create(MSG_AGENT_DISCONNECT, "mist-0", "broker")
        await router.handle(disc_msg, mock_conn)
        assert registry.get_by_conn(mock_conn) is None


# ── Agent listing ────────────────────────────────────────────────────


class TestAgentList:
    async def test_list_returns_catalog(self, router, mock_conn, registry):
        # Register an agent
        reg_msg = Message.create(
            MSG_AGENT_REGISTER, "client", "broker",
            {"name": "mist", "commands": ["/sync"]},
        )
        await router.handle(reg_msg, mock_conn)

        mock_conn.send.reset_mock()
        list_msg = Message.create(MSG_AGENT_LIST, "widget", "broker")
        await router.handle(list_msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_AGENT_CATALOG
        assert len(reply.payload["agents"]) == 1
        assert reply.payload["agents"][0]["agent_id"] == "mist-0"


# ── Command routing ──────────────────────────────────────────────────


class TestCommandRouting:
    async def test_command_forwarded_to_agent(self, router, mock_conn, mock_conn2, registry):
        # Register agent on mock_conn2
        entry = registry.register(mock_conn2, {"name": "mist", "commands": []})

        # Send command from mock_conn (widget) to the agent
        cmd_msg = Message.create(
            MSG_COMMAND, "widget", "mist-0", {"text": "hello"},
        )
        await router.handle(cmd_msg, mock_conn)

        # Should be forwarded to agent's connection
        assert mock_conn2.send.called
        forwarded = _get_reply(mock_conn2)
        assert forwarded.type == MSG_COMMAND
        assert forwarded.payload["text"] == "hello"

        # Pending should be tracked
        assert cmd_msg.id in router._pending

    async def test_command_to_unknown_agent(self, router, mock_conn):
        cmd_msg = Message.create(
            MSG_COMMAND, "widget", "nonexistent", {"text": "hello"},
        )
        await router.handle(cmd_msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_ERROR
        assert "unknown agent" in reply.payload["error"]

    async def test_response_routed_back(self, router, mock_conn, mock_conn2, registry):
        # Register agent
        registry.register(mock_conn2, {"name": "mist"})

        # Send command from widget (mock_conn)
        cmd_msg = Message.create(MSG_COMMAND, "widget", "mist-0", {"text": "hi"})
        await router.handle(cmd_msg, mock_conn)
        mock_conn.send.reset_mock()

        # Agent sends response
        resp_msg = Message.create(
            MSG_RESPONSE, "mist-0", "widget",
            {"text": "hello back"},
            reply_to=cmd_msg.id,
        )
        await router.handle(resp_msg, mock_conn2)

        # Response should be forwarded back to widget
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_RESPONSE
        assert reply.payload["text"] == "hello back"

        # Pending should be cleaned up
        assert cmd_msg.id not in router._pending

    async def test_response_chunk_keeps_pending(self, router, mock_conn, mock_conn2, registry):
        registry.register(mock_conn2, {"name": "mist"})

        cmd_msg = Message.create(MSG_COMMAND, "widget", "mist-0", {"text": "hi"})
        await router.handle(cmd_msg, mock_conn)
        mock_conn.send.reset_mock()

        # Agent sends chunk
        chunk_msg = Message.create(
            MSG_RESPONSE_CHUNK, "mist-0", "widget",
            {"text": "partial"},
            reply_to=cmd_msg.id,
        )
        await router.handle(chunk_msg, mock_conn2)

        # Forwarded but pending kept
        assert mock_conn.send.called
        assert cmd_msg.id in router._pending

    async def test_response_end_removes_pending(self, router, mock_conn, mock_conn2, registry):
        registry.register(mock_conn2, {"name": "mist"})

        cmd_msg = Message.create(MSG_COMMAND, "widget", "mist-0", {"text": "hi"})
        await router.handle(cmd_msg, mock_conn)
        mock_conn.send.reset_mock()

        # Agent sends response.end
        end_msg = Message.create(
            MSG_RESPONSE_END, "mist-0", "widget",
            {},
            reply_to=cmd_msg.id,
        )
        await router.handle(end_msg, mock_conn2)

        assert mock_conn.send.called
        assert cmd_msg.id not in router._pending


# ── Service routing ──────────────────────────────────────────────────


class TestServiceRouting:
    async def test_service_request_delegates(self, router, mock_conn, services):
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "tasks", "action": "list"},
        )
        await router.handle(msg, mock_conn)
        services.handle.assert_awaited_once_with(msg, mock_conn)

    async def test_llm_request_delegates(self, router, mock_conn, llm):
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "llm", "action": "chat", "params": {"prompt": "hi"}},
        )
        await router.handle(msg, mock_conn)
        llm.handle.assert_awaited_once_with(msg, mock_conn)


# ── Unknown message type ─────────────────────────────────────────────


class TestUnknownType:
    async def test_unknown_type_sends_error(self, router, mock_conn):
        msg = Message.create("bogus.type", "test", "broker")
        await router.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_ERROR
        assert "unknown message type" in reply.payload["error"]
