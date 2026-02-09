"""Tests for mist_core.broker.router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from mist_core.protocol import (
    Message,
    MSG_AGENT_CATALOG,
    MSG_AGENT_LIST,
    MSG_AGENT_MESSAGE,
    MSG_AGENT_READY,
    MSG_AGENT_REGISTER,
    MSG_COMMAND,
    MSG_ERROR,
    MSG_RESPONSE,
    MSG_SERVICE_REQUEST,
)
from mist_core.transport import Connection

from mist_core.broker.registry import AgentRegistry
from mist_core.broker.router import MessageRouter
from mist_core.broker.services import ServiceDispatcher


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
def router(registry, services):
    return MessageRouter(registry, services)


def _get_reply(conn) -> Message:
    assert conn.send.called
    return conn.send.call_args[0][0]


class TestRegister:
    async def test_register_sends_ready(self, router, mock_conn, registry):
        msg = Message.create(
            MSG_AGENT_REGISTER, "client", "broker",
            {"name": "mist", "commands": [{"name": "note"}]},
        )
        await router.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_AGENT_READY
        assert reply.payload["agent_id"] == "mist-0"
        assert registry.get_by_id("mist-0") is not None

    async def test_disconnect_removes_agent(self, router, mock_conn, registry):
        reg_msg = Message.create(
            MSG_AGENT_REGISTER, "client", "broker", {"name": "mist"},
        )
        await router.handle(reg_msg, mock_conn)
        disc_msg = Message.create("agent.disconnect", "mist-0", "broker")
        await router.handle(disc_msg, mock_conn)
        assert registry.get_by_conn(mock_conn) is None


class TestAgentList:
    async def test_list_returns_catalog(self, router, mock_conn, registry):
        reg_msg = Message.create(
            MSG_AGENT_REGISTER, "client", "broker",
            {"name": "mist", "commands": [{"name": "note"}]},
        )
        await router.handle(reg_msg, mock_conn)
        mock_conn.send.reset_mock()

        list_msg = Message.create(MSG_AGENT_LIST, "widget", "broker")
        await router.handle(list_msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_AGENT_CATALOG
        assert len(reply.payload["agents"]) == 1


class TestCommandRouting:
    async def test_command_forwarded_to_agent(self, router, mock_conn, mock_conn2, registry):
        registry.register(mock_conn2, {"name": "mist"})
        cmd_msg = Message.create(MSG_COMMAND, "widget", "mist-0", {"text": "hello"})
        await router.handle(cmd_msg, mock_conn)
        forwarded = _get_reply(mock_conn2)
        assert forwarded.type == MSG_COMMAND
        assert forwarded.payload["text"] == "hello"

    async def test_command_to_unknown_agent(self, router, mock_conn):
        cmd_msg = Message.create(MSG_COMMAND, "widget", "nonexistent", {"text": "hi"})
        await router.handle(cmd_msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_ERROR
        assert "unknown agent" in reply.payload["error"]

    async def test_response_routed_back(self, router, mock_conn, mock_conn2, registry):
        registry.register(mock_conn2, {"name": "mist"})
        cmd_msg = Message.create(MSG_COMMAND, "widget", "mist-0", {"text": "hi"})
        await router.handle(cmd_msg, mock_conn)
        mock_conn.send.reset_mock()

        resp_msg = Message.create(
            MSG_RESPONSE, "mist-0", "widget",
            {"text": "hello back"}, reply_to=cmd_msg.id,
        )
        await router.handle(resp_msg, mock_conn2)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_RESPONSE
        assert reply.payload["text"] == "hello back"
        assert cmd_msg.id not in router._pending


class TestAdminHandler:
    async def test_command_to_admin_calls_handler(self, router, registry):
        admin_handler = AsyncMock()
        router.set_admin_handler(admin_handler)
        registry.register(None, {"name": "admin"}, privileged=True)

        origin = MagicMock(spec=Connection)
        origin.send = AsyncMock()
        cmd = Message.create(MSG_COMMAND, "widget", "admin-0", {"text": "help"})
        await router.handle(cmd, origin)
        admin_handler.assert_awaited_once()
        # The message passed to admin handler should be the command
        passed_msg = admin_handler.call_args[0][0]
        assert passed_msg.payload["text"] == "help"


class TestInterAgentMessage:
    async def test_agent_message_forwarded(self, router, mock_conn, mock_conn2, registry):
        registry.register(mock_conn, {"name": "notes"})
        registry.register(mock_conn2, {"name": "science"})
        msg = Message.create(MSG_AGENT_MESSAGE, "notes-0", "science-0", {"data": "hi"})
        await router.handle(msg, mock_conn)
        forwarded = _get_reply(mock_conn2)
        assert forwarded.type == MSG_AGENT_MESSAGE
        assert forwarded.payload["data"] == "hi"

    async def test_agent_message_to_unknown(self, router, mock_conn, registry):
        registry.register(mock_conn, {"name": "notes"})
        msg = Message.create(MSG_AGENT_MESSAGE, "notes-0", "nonexistent", {"data": "hi"})
        await router.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_ERROR


class TestServiceRouting:
    async def test_service_request_delegates(self, router, mock_conn, services):
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "tasks", "action": "list"},
        )
        await router.handle(msg, mock_conn)
        services.handle.assert_awaited_once()


class TestUnknownType:
    async def test_unknown_type_sends_error(self, router, mock_conn):
        msg = Message.create("bogus.type", "test", "broker")
        await router.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_ERROR
        assert "unknown message type" in reply.payload["error"]
