"""Integration tests: full broker with real clients over Unix socket."""

from __future__ import annotations

import asyncio

import pytest

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
from mist_core.transport import Client


# ── Registration ─────────────────────────────────────────────────────


class TestRegistration:
    async def test_register_returns_ready(self, client_for_broker):
        client = client_for_broker
        msg = Message.create(
            MSG_AGENT_REGISTER, "test", "broker",
            {"name": "mist", "commands": ["/reflect"]},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.type == MSG_AGENT_READY
        assert reply.payload["agent_id"] == "mist-0"

    async def test_register_two_agents(self, running_broker):
        _, socket_path = running_broker
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


# ── Service requests ─────────────────────────────────────────────────


class TestServiceRequests:
    async def test_task_round_trip(self, client_for_broker):
        client = client_for_broker

        # Create a task
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "tasks", "action": "create", "params": {"title": "Test task"}},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.type == MSG_SERVICE_RESPONSE
        task_id = reply.payload["result"]["task_id"]

        # List tasks
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "tasks", "action": "list", "params": {}},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.type == MSG_SERVICE_RESPONSE
        tasks = reply.payload["result"]
        assert any(t["id"] == task_id and t["title"] == "Test task" for t in tasks)

    async def test_settings_round_trip(self, client_for_broker):
        client = client_for_broker

        # Set a setting
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "settings", "action": "set", "params": {"key": "model", "value": "test-model"}},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.type == MSG_SERVICE_RESPONSE

        # Get it back
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "settings", "action": "get", "params": {"key": "model"}},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.payload["result"] == "test-model"

    async def test_storage_save_and_parse(self, client_for_broker):
        client = client_for_broker

        # Save raw input
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "storage", "action": "save_raw_input", "params": {"text": "hello", "source": "test"}},
        )
        reply = await client.request(msg, timeout=5.0)
        assert reply.type == MSG_SERVICE_RESPONSE

        # Parse rawlog
        msg = Message.create(
            MSG_SERVICE_REQUEST, "test", "broker",
            {"service": "storage", "action": "parse_rawlog", "params": {}},
        )
        reply = await client.request(msg, timeout=5.0)
        entries = reply.payload["result"]
        assert len(entries) == 1
        assert entries[0]["text"] == "hello"


# ── Command routing ──────────────────────────────────────────────────


class TestCommandRouting:
    async def test_command_routed_to_agent(self, running_broker):
        """Widget sends command -> broker -> agent -> broker -> widget."""
        _, socket_path = running_broker

        # Agent connects and registers
        agent = Client(path=socket_path)
        await agent.connect()
        reg_reply = await agent.request(Message.create(
            MSG_AGENT_REGISTER, "agent", "broker",
            {"name": "echo", "commands": ["/echo"]},
        ), timeout=5.0)
        agent_id = reg_reply.payload["agent_id"]

        # Widget connects
        widget = Client(path=socket_path)
        await widget.connect()

        try:
            # Widget sends command to agent
            cmd = Message.create(
                MSG_COMMAND, "widget", agent_id,
                {"text": "echo this"},
            )
            await widget.send(cmd)

            # Agent receives the command
            received = await asyncio.wait_for(agent.recv(), timeout=5.0)
            assert received is not None
            assert received.type == MSG_COMMAND
            assert received.payload["text"] == "echo this"

            # Agent sends response back
            resp = Message.reply(
                received, agent_id, MSG_RESPONSE,
                {"text": "echoed: echo this"},
            )
            await agent.send(resp)

            # Widget receives the response
            result = await asyncio.wait_for(widget.recv(), timeout=5.0)
            assert result is not None
            assert result.type == MSG_RESPONSE
            assert result.payload["text"] == "echoed: echo this"
        finally:
            agent.close()
            widget.close()
            await agent.wait_closed()
            await widget.wait_closed()


# ── Agent catalog ────────────────────────────────────────────────────


class TestAgentCatalog:
    async def test_list_agents(self, running_broker):
        _, socket_path = running_broker

        # Register an agent
        agent = Client(path=socket_path)
        await agent.connect()
        await agent.request(Message.create(
            MSG_AGENT_REGISTER, "a", "broker",
            {"name": "mist", "commands": ["/reflect"], "description": "Main"},
        ), timeout=5.0)

        # Widget asks for catalog
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
            assert agents[0]["commands"] == ["/reflect"]
        finally:
            agent.close()
            widget.close()
            await agent.wait_closed()
            await widget.wait_closed()
