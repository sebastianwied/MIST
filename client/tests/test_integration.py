"""Integration test: real core broker + real agent via client lib."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from mist_client.agent import AgentBase
from mist_client.protocol import (
    Message,
    MSG_AGENT_REGISTER,
    MSG_AGENT_READY,
    MSG_COMMAND,
    MSG_RESPONSE,
    RESP_TEXT,
    RESP_TABLE,
    decode_message,
    encode_message,
)

# Import core (available because both packages are installed in the same venv)
from mist_core.db import Database
from mist_core.paths import Paths
from mist_core.storage.settings import Settings
from mist_core.broker.registry import AgentRegistry
from mist_core.broker.router import MessageRouter
from mist_core.broker.services import ServiceDispatcher
from mist_core.transport import Server, Client


@pytest.fixture
def sock_path():
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        yield Path(td) / "mist.sock"


@pytest.fixture
async def running_core(tmp_path, sock_path):
    """Start a real core broker."""
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


class NotesTestAgent(AgentBase):
    """Minimal notes agent for integration testing."""

    def __init__(self, socket_path):
        super().__init__(socket_path)
        self.commands_received = []

    def manifest(self):
        return {
            "name": "notes",
            "description": "Test notes agent",
            "commands": [
                {"name": "note", "description": "Save a note"},
                {"name": "topics", "description": "List topics"},
            ],
            "panels": [{"id": "chat", "label": "Notes", "type": "chat", "default": True}],
        }

    async def handle_command(self, msg):
        self.commands_received.append(msg)
        command = msg.payload.get("command", "")

        if command == "note":
            text = msg.payload.get("args", {}).get("text", "")
            await self.client.save_raw_input(text)
            await self.client.respond_text(msg, f"Saved: {text}")

        elif command == "topics":
            topics = await self.client.load_topic_index()
            items = [t["name"] for t in topics]
            await self.client.respond_list(msg, items, title="Topics")

        else:
            await self.client.respond_text(msg, f"Unknown: {command}")


async def test_full_stack_agent(running_core, sock_path):
    """Full integration: core broker + agent client lib + service calls."""
    _, socket_path, _ = running_core

    # Start agent
    agent = NotesTestAgent(socket_path=socket_path)
    agent_task = asyncio.create_task(agent.run())

    # Wait for registration
    await asyncio.sleep(0.1)
    assert agent.agent_id == "notes-0"

    # Simulate a UI client sending a command
    ui = Client(path=socket_path)
    await ui.connect()

    try:
        # Send "note" command
        cmd = Message.create(
            MSG_COMMAND, "ui", "notes-0",
            {"command": "note", "args": {"text": "hello world"}},
        )
        await ui.send(cmd)

        # Receive response
        resp = await asyncio.wait_for(ui.recv(), timeout=5.0)
        assert resp.type == MSG_RESPONSE
        assert resp.payload["type"] == RESP_TEXT
        assert "Saved: hello world" in resp.payload["content"]["text"]

        # Verify note was actually saved via service
        # Send another command to check topics (will be empty but verifies the path)
        cmd2 = Message.create(
            MSG_COMMAND, "ui", "notes-0",
            {"command": "topics"},
        )
        await ui.send(cmd2)
        resp2 = await asyncio.wait_for(ui.recv(), timeout=5.0)
        assert resp2.type == MSG_RESPONSE

    finally:
        ui.close()
        await ui.wait_closed()
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
