"""Integration tests: full broker with real clients over Unix socket."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from mist_core.db import Database
from mist_core.paths import Paths
from mist_core.protocol import (
    Message,
    MSG_AGENT_CATALOG,
    MSG_AGENT_LIST,
    MSG_AGENT_READY,
    MSG_AGENT_REGISTER,
    MSG_COMMAND,
    MSG_RESPONSE,
    MSG_SERVICE_REQUEST,
    MSG_SERVICE_RESPONSE,
)
from mist_core.storage.settings import Settings
from mist_core.transport import Client, Server

from mist_core.broker.registry import AgentRegistry
from mist_core.broker.router import MessageRouter
from mist_core.broker.services import ServiceDispatcher


@pytest.fixture
def sock_path():
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        yield Path(td) / "mist.sock"


@pytest.fixture
async def running_broker(tmp_path, sock_path):
    """Start a real broker on a temp socket."""
    paths = Paths(root=tmp_path / "data")
    db = Database(paths.db)
    db.connect()
    db.init_schema()
    settings = Settings(paths)
    registry = AgentRegistry()
    services = ServiceDispatcher(paths, db, settings)
    router = MessageRouter(registry, services)
    server = Server(router.handle, path=sock_path)
    await server.start()
    task = asyncio.create_task(server.serve_forever())
    yield router, sock_path, registry
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await server.stop()
    db.close()


@pytest.fixture
async def client_for_broker(running_broker):
    _, socket_path, _ = running_broker
    client = Client(path=socket_path)
    await client.connect()
    yield client
    client.close()
    await client.wait_closed()


class TestRegistration:
    async def test_register_returns_ready(self, client_for_broker):
        client = client_for_broker
        msg = Message.create(
            MSG_AGENT_REGISTER, "test", "broker",
            {"name": "mist", "commands": [{"name": "note"}]},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.type == MSG_AGENT_READY
        assert reply.payload["agent_id"] == "mist-0"

    async def test_register_two_agents(self, running_broker):
        _, socket_path, _ = running_broker
        c1 = Client(path=socket_path)
        c2 = Client(path=socket_path)
        await c1.connect()
        await c2.connect()
        try:
            r1 = await c1.request(Message.create(
                MSG_AGENT_REGISTER, "a", "broker", {"name": "mist"},
            ), timeout=5.0)
            r2 = await c2.request(Message.create(
                MSG_AGENT_REGISTER, "b", "broker", {"name": "mist"},
            ), timeout=5.0)
            assert r1.payload["agent_id"] == "mist-0"
            assert r2.payload["agent_id"] == "mist-1"
        finally:
            c1.close()
            c2.close()
            await c1.wait_closed()
            await c2.wait_closed()


class TestServiceRequests:
    async def test_task_round_trip(self, client_for_broker):
        client = client_for_broker
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "tasks", "action": "create", "params": {"title": "Test task"}},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.type == MSG_SERVICE_RESPONSE
        task_id = reply.payload["result"]["task_id"]

        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "tasks", "action": "list", "params": {}},
        )
        reply = await client.request(msg, timeout=5.0)
        tasks = reply.payload["result"]
        assert any(t["id"] == task_id for t in tasks)

    async def test_settings_round_trip(self, client_for_broker):
        client = client_for_broker
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "settings", "action": "set",
             "params": {"key": "model", "value": "test-model"}},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.type == MSG_SERVICE_RESPONSE

        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "settings", "action": "get", "params": {"key": "model"}},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.payload["result"] == "test-model"


class TestCommandRouting:
    async def test_command_routed_to_agent(self, running_broker):
        _, socket_path, _ = running_broker

        agent = Client(path=socket_path)
        await agent.connect()
        reg_reply = await agent.request(Message.create(
            MSG_AGENT_REGISTER, "agent", "broker",
            {"name": "echo", "commands": [{"name": "echo"}]},
        ), timeout=5.0)
        agent_id = reg_reply.payload["agent_id"]

        widget = Client(path=socket_path)
        await widget.connect()
        try:
            cmd = Message.create(MSG_COMMAND, "widget", agent_id, {"text": "echo this"})
            await widget.send(cmd)

            received = await asyncio.wait_for(agent.recv(), timeout=5.0)
            assert received.type == MSG_COMMAND
            assert received.payload["text"] == "echo this"

            resp = Message.reply(received, agent_id, MSG_RESPONSE, {"text": "echoed"})
            await agent.send(resp)

            result = await asyncio.wait_for(widget.recv(), timeout=5.0)
            assert result.type == MSG_RESPONSE
            assert result.payload["text"] == "echoed"
        finally:
            agent.close()
            widget.close()
            await agent.wait_closed()
            await widget.wait_closed()


class TestAgentCatalog:
    async def test_list_agents(self, running_broker):
        _, socket_path, _ = running_broker

        agent = Client(path=socket_path)
        await agent.connect()
        await agent.request(Message.create(
            MSG_AGENT_REGISTER, "a", "broker",
            {"name": "mist", "commands": [{"name": "note"}], "description": "Main"},
        ), timeout=5.0)

        widget = Client(path=socket_path)
        await widget.connect()
        try:
            reply = await widget.request(
                Message.create(MSG_AGENT_LIST, "widget", "broker"),
                timeout=5.0,
            )
            assert reply.type == MSG_AGENT_CATALOG
            agents = reply.payload["agents"]
            assert len(agents) == 1
            assert agents[0]["agent_id"] == "mist-0"
        finally:
            agent.close()
            widget.close()
            await agent.wait_closed()
            await widget.wait_closed()
