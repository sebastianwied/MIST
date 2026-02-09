"""Tests for admin agent routing — @mention, command matching, forwarding."""

from __future__ import annotations

import asyncio

import pytest

from mist_core.admin.agent import AdminAgent
from mist_core.broker.registry import AgentRegistry
from mist_core.broker.router import MessageRouter, PendingCommand
from mist_core.broker.services import ServiceDispatcher
from mist_core.db import Database
from mist_core.llm.client import OllamaClient
from mist_core.llm.queue import LLMQueue
from mist_core.paths import Paths
from mist_core.protocol import (
    Message,
    MSG_COMMAND,
    MSG_RESPONSE,
    RESP_ERROR,
    RESP_TEXT,
)
from mist_core.storage.settings import Settings


class FakeConn:
    """Minimal fake connection that captures sent messages."""

    def __init__(self):
        self.sent: list[Message] = []

    async def send(self, msg: Message) -> None:
        self.sent.append(msg)


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
def registry():
    return AgentRegistry()


@pytest.fixture
def services(paths, db, settings):
    return ServiceDispatcher(paths, db, settings)


@pytest.fixture
def router(registry, services):
    return MessageRouter(registry, services)


@pytest.fixture
def admin(paths, db, settings, registry, services, router):
    llm_client = OllamaClient(settings)
    llm_queue = LLMQueue(llm_client)
    agent = AdminAgent(
        paths=paths, db=db, settings=settings,
        llm_queue=llm_queue, registry=registry,
        services=services, router=router,
    )
    agent.register()
    return agent


def _make_command(command: str = "", text: str = "", args: dict | None = None, to: str = "admin-0") -> Message:
    payload: dict = {}
    if command:
        payload["command"] = command
    if text:
        payload["text"] = text
    if args:
        payload["args"] = args
    return Message.create(MSG_COMMAND, "ui", to, payload)


class TestMentionRouting:
    async def test_at_mention_forwards_to_agent(self, router, admin, registry):
        """@notes <text> should forward the command to the notes agent."""
        notes_conn = FakeConn()
        registry.register(notes_conn, {
            "name": "notes",
            "commands": [{"name": "note", "description": "Save a note"}],
        })

        ui_conn = FakeConn()
        msg = _make_command(command="@notes", text="hello world")

        # Set up pending like the router would
        router._pending[msg.id] = PendingCommand(
            msg_id=msg.id, origin_conn=ui_conn, target_agent_id=admin.agent_id,
        )
        await admin.handle(msg)

        # The command should have been forwarded to notes agent
        assert len(notes_conn.sent) == 1
        fwd = notes_conn.sent[0]
        assert fwd.type == MSG_COMMAND
        assert fwd.to == "notes-0"

    async def test_at_mention_unknown_agent(self, router, admin):
        """@unknown should return an error."""
        ui_conn = FakeConn()
        msg = _make_command(command="@nonexistent", text="hello")

        router._pending[msg.id] = PendingCommand(
            msg_id=msg.id, origin_conn=ui_conn, target_agent_id=admin.agent_id,
        )
        await admin.handle(msg)

        assert len(ui_conn.sent) == 1
        resp = ui_conn.sent[0]
        assert resp.payload["type"] == RESP_ERROR
        assert "nonexistent" in resp.payload["content"]["message"]

    async def test_at_mention_by_agent_id(self, router, admin, registry):
        """@notes-0 should also work (by agent_id)."""
        notes_conn = FakeConn()
        registry.register(notes_conn, {
            "name": "notes",
            "commands": [{"name": "note", "description": "Save a note"}],
        })

        ui_conn = FakeConn()
        msg = _make_command(command="@notes-0", text="hello")

        router._pending[msg.id] = PendingCommand(
            msg_id=msg.id, origin_conn=ui_conn, target_agent_id=admin.agent_id,
        )
        await admin.handle(msg)

        assert len(notes_conn.sent) == 1


class TestCommandMatching:
    async def test_command_forwarded_to_owner(self, router, admin, registry):
        """A command registered by another agent should be forwarded there."""
        notes_conn = FakeConn()
        registry.register(notes_conn, {
            "name": "notes",
            "commands": [{"name": "note", "description": "Save a note"}],
        })

        ui_conn = FakeConn()
        msg = _make_command(command="note", text="hello world")

        router._pending[msg.id] = PendingCommand(
            msg_id=msg.id, origin_conn=ui_conn, target_agent_id=admin.agent_id,
        )
        await admin.handle(msg)

        assert len(notes_conn.sent) == 1
        fwd = notes_conn.sent[0]
        assert fwd.type == MSG_COMMAND
        assert fwd.to == "notes-0"

    async def test_admin_command_not_forwarded(self, router, admin, registry):
        """Admin's own commands should not be forwarded, even if another agent
        also has a 'help' command."""
        ext_conn = FakeConn()
        registry.register(ext_conn, {
            "name": "other",
            "commands": [{"name": "help", "description": "Other help"}],
        })

        ui_conn = FakeConn()
        msg = _make_command(command="help")

        router._pending[msg.id] = PendingCommand(
            msg_id=msg.id, origin_conn=ui_conn, target_agent_id=admin.agent_id,
        )
        await admin.handle(msg)

        # help should be handled by admin, not forwarded
        assert len(ext_conn.sent) == 0
        assert len(ui_conn.sent) == 1
        assert "Available commands" in ui_conn.sent[0].payload["content"]["text"]


class TestForwardCommand:
    async def test_forward_routes_response_back_to_ui(self, router, admin, registry):
        """When a command is forwarded and the agent responds, the UI should
        receive the response."""
        notes_conn = FakeConn()
        registry.register(notes_conn, {
            "name": "notes",
            "commands": [{"name": "note", "description": "Save a note"}],
        })

        ui_conn = FakeConn()
        msg = _make_command(command="note", text="test")

        # Simulate full router flow
        router._pending[msg.id] = PendingCommand(
            msg_id=msg.id, origin_conn=ui_conn, target_agent_id=admin.agent_id,
        )
        await admin.handle(msg)

        # notes agent received the forwarded command
        assert len(notes_conn.sent) == 1
        fwd = notes_conn.sent[0]

        # Notes agent sends a response
        response = Message.reply(fwd, "notes-0", MSG_RESPONSE, {
            "type": RESP_TEXT,
            "content": {"text": "Saved: test", "format": "plain"},
        })
        # Route the response through the router
        await router._on_response(response, notes_conn)

        # UI should receive the response
        assert len(ui_conn.sent) == 1
        assert ui_conn.sent[0].payload["content"]["text"] == "Saved: test"

    async def test_forward_to_disconnected_agent(self, router, admin, registry):
        """Forwarding to an agent with no connection should error."""
        # Register agent with conn, then remove the conn
        registry.register(None, {
            "name": "dead",
            "commands": [{"name": "ghost", "description": "Dead cmd"}],
        })

        ui_conn = FakeConn()
        msg = _make_command(command="ghost")

        router._pending[msg.id] = PendingCommand(
            msg_id=msg.id, origin_conn=ui_conn, target_agent_id=admin.agent_id,
        )
        await admin.handle(msg)

        # Should get an error back
        assert len(ui_conn.sent) == 1
        resp = ui_conn.sent[0]
        assert "no connection" in resp.payload.get("error", "")


class TestTextFallthrough:
    async def test_unknown_command_treated_as_text(self, router, admin, registry):
        """An unrecognised bare command should be treated as free text.
        Mock the LLM queue to avoid real LLM calls."""
        from unittest.mock import AsyncMock, patch

        ui_conn = FakeConn()
        # Use text-only payload (no structured command)
        msg = Message.create(MSG_COMMAND, "ui", "admin-0", {"text": "thinking about life"})

        router._pending[msg.id] = PendingCommand(
            msg_id=msg.id, origin_conn=ui_conn, target_agent_id=admin.agent_id,
        )

        with patch.object(admin._llm_queue, "submit", new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = "A thought about life."
            await admin.handle(msg)

        # Should get a text response from the mocked LLM
        assert len(ui_conn.sent) >= 1
        resp = ui_conn.sent[0]
        assert resp.payload["type"] == RESP_TEXT
        assert "life" in resp.payload["content"]["text"]
