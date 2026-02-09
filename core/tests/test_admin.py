"""Tests for the admin agent — help, status, tasks, events, settings, set."""

from __future__ import annotations

import asyncio

import pytest

from mist_core.admin.agent import AdminAgent, ADMIN_MANIFEST
from mist_core.broker.registry import AgentRegistry
from mist_core.broker.router import MessageRouter
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
    RESP_LIST,
    RESP_TABLE,
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


async def _send_and_capture(router, admin, msg) -> Message:
    """Send a command through the router and capture the response."""
    conn = FakeConn()
    # Simulate what the router does: track pending, call admin handler
    from mist_core.broker.router import PendingCommand
    router._pending[msg.id] = PendingCommand(
        msg_id=msg.id, origin_conn=conn, target_agent_id=admin.agent_id,
    )
    await admin.handle(msg)
    assert len(conn.sent) >= 1, "admin did not send a response"
    return conn.sent[0]


class TestAdminHelp:
    async def test_help_returns_text(self, router, admin):
        msg = _make_command(command="help")
        resp = await _send_and_capture(router, admin, msg)
        assert resp.type == MSG_RESPONSE
        assert resp.payload["type"] == RESP_TEXT
        assert "Available commands" in resp.payload["content"]["text"]

    async def test_help_includes_admin_commands(self, router, admin):
        msg = _make_command(command="help")
        resp = await _send_and_capture(router, admin, msg)
        text = resp.payload["content"]["text"]
        assert "help" in text
        assert "status" in text
        assert "tasks" in text

    async def test_help_includes_external_agent_commands(self, router, admin, registry):
        # Register a fake external agent
        registry.register(FakeConn(), {
            "name": "notes",
            "commands": [{"name": "note", "description": "Save a note"}],
        })
        msg = _make_command(command="help")
        resp = await _send_and_capture(router, admin, msg)
        text = resp.payload["content"]["text"]
        assert "notes" in text
        assert "note" in text


class TestAdminStatus:
    async def test_status_basic(self, router, admin):
        msg = _make_command(command="status")
        resp = await _send_and_capture(router, admin, msg)
        assert resp.payload["type"] == RESP_TEXT
        text = resp.payload["content"]["text"]
        assert "Agents:" in text
        assert "Tasks:" in text
        assert "Events:" in text


class TestAdminTasks:
    async def test_tasks_empty(self, router, admin):
        msg = _make_command(command="tasks")
        resp = await _send_and_capture(router, admin, msg)
        assert resp.payload["type"] == RESP_TEXT
        assert "No tasks" in resp.payload["content"]["text"]

    async def test_tasks_with_data(self, router, admin, services):
        await asyncio.to_thread(services._tasks.create, title="Buy milk")
        await asyncio.to_thread(services._tasks.create, title="Read paper", due_date="2025-12-31")
        msg = _make_command(command="tasks")
        resp = await _send_and_capture(router, admin, msg)
        assert resp.payload["type"] == RESP_TABLE
        content = resp.payload["content"]
        assert "ID" in content["columns"]
        assert len(content["rows"]) == 2


class TestAdminEvents:
    async def test_events_empty(self, router, admin):
        msg = _make_command(command="events")
        resp = await _send_and_capture(router, admin, msg)
        assert resp.payload["type"] == RESP_TEXT
        assert "No upcoming" in resp.payload["content"]["text"]


class TestAdminAgents:
    async def test_agents_list(self, router, admin, registry):
        msg = _make_command(command="agents")
        resp = await _send_and_capture(router, admin, msg)
        assert resp.payload["type"] == RESP_LIST
        items = resp.payload["content"]["items"]
        assert any("admin-0" in item for item in items)


class TestAdminSettings:
    async def test_settings_empty(self, router, admin):
        msg = _make_command(command="settings")
        resp = await _send_and_capture(router, admin, msg)
        assert resp.payload["type"] == RESP_TEXT

    async def test_set_and_show(self, router, admin):
        # Set a value
        set_msg = _make_command(command="set", args={"key": "model", "value": "llama3"})
        resp1 = await _send_and_capture(router, admin, set_msg)
        assert "set to" in resp1.payload["content"]["text"]

        # Show settings
        show_msg = _make_command(command="settings")
        resp2 = await _send_and_capture(router, admin, show_msg)
        assert "llama3" in resp2.payload["content"]["text"]

    async def test_set_from_text(self, router, admin):
        msg = _make_command(command="set", text="model llama3")
        resp = await _send_and_capture(router, admin, msg)
        assert "set to" in resp.payload["content"]["text"]

    async def test_set_missing_value(self, router, admin):
        msg = _make_command(command="set", text="model")
        resp = await _send_and_capture(router, admin, msg)
        assert resp.payload["type"] == RESP_ERROR


class TestAdminManifest:
    def test_manifest_has_required_fields(self):
        assert ADMIN_MANIFEST["name"] == "admin"
        assert len(ADMIN_MANIFEST["commands"]) > 0
        assert len(ADMIN_MANIFEST["panels"]) > 0

    def test_admin_registers_as_privileged(self, registry, router, paths, db, settings):
        llm_queue = LLMQueue(OllamaClient(settings))
        services = ServiceDispatcher(paths, db, settings)
        agent = AdminAgent(
            paths=paths, db=db, settings=settings,
            llm_queue=llm_queue, registry=registry,
            services=services, router=router,
        )
        agent_id = agent.register()
        assert agent_id == "admin-0"
        entry = registry.get_by_id("admin-0")
        assert entry is not None
        assert entry.privileged is True
        assert entry.conn is None
