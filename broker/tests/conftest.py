"""Shared fixtures for broker tests."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from mist_core.protocol import Message
from mist_core.transport import Connection, Server, Client

from mist_broker.broker import Broker


@pytest.fixture
def tmp_socket(tmp_path):
    """Return a temporary socket path short enough for macOS (max 104 chars)."""
    # tmp_path can be long; use /tmp for shorter paths on macOS
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        yield Path(td) / "mist.sock"


@pytest.fixture
def mock_conn():
    """Return a mock Connection with async send."""
    conn = MagicMock(spec=Connection)
    conn.send = AsyncMock()
    return conn


@pytest.fixture
async def running_broker(tmp_socket, tmp_path, monkeypatch):
    """Start a real broker on a temp socket and yield (broker, socket_path).

    Patches data paths so tests don't touch real data.
    """
    # Redirect all data paths to temp directory
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

    # Run serve_forever in background
    task = asyncio.create_task(broker._server.serve_forever())
    yield broker, tmp_socket

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await broker.shutdown()


@pytest.fixture
async def client_for_broker(running_broker):
    """Return a connected Client for the running broker."""
    broker, socket_path = running_broker
    client = Client(path=socket_path)
    await client.connect()
    yield client
    client.close()
    await client.wait_closed()
