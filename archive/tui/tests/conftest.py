"""Shared fixtures for TUI tests."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from mist_core.protocol import (
    Message,
    MSG_AGENT_REGISTER,
    MSG_AGENT_READY,
    MSG_COMMAND,
    MSG_RESPONSE,
)
from mist_core.transport import Client


@pytest.fixture
def tmp_socket():
    """Return a temporary socket path short enough for macOS (max 104 chars)."""
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        yield Path(td) / "mist.sock"


@pytest.fixture
async def running_broker(tmp_socket, tmp_path, monkeypatch):
    """Start a real broker on a temp socket and yield (broker, socket_path).

    Patches data paths so tests don't touch real data.
    Requires mist-broker to be installed.
    """
    from mist_broker.broker import Broker

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

    broker = Broker(socket_path=tmp_socket)
    broker._services.initialize()
    await broker._server.start()

    task = asyncio.create_task(broker._server.serve_forever())
    yield broker, tmp_socket

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await broker.shutdown()


@pytest.fixture
async def echo_agent(running_broker):
    """Register an echo agent that replies 'echo: <text>' to every command.

    Yields (agent_id, socket_path).
    """
    _, socket_path = running_broker
    client = Client(path=socket_path)
    await client.connect()

    # Register
    reg_msg = Message.create(
        MSG_AGENT_REGISTER, "echo-agent", "broker",
        {"name": "echo", "commands": ["echo"], "description": "Echo agent"},
    )
    reply = await client.request(reg_msg)
    assert reply.type == MSG_AGENT_READY
    agent_id = reply.payload["agent_id"]

    # Echo loop as background task
    async def _echo_loop():
        try:
            async for msg in client:
                if msg.type == MSG_COMMAND:
                    text = msg.payload.get("text", "")
                    resp = Message.reply(
                        msg, agent_id, MSG_RESPONSE,
                        {"text": f"echo: {text}"},
                    )
                    await client.send(resp)
        except asyncio.CancelledError:
            pass

    loop_task = asyncio.create_task(_echo_loop())
    yield agent_id, socket_path

    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass
    client.close()
    await client.wait_closed()
