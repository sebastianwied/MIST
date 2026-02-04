"""Tests for BrokerClient against a real broker + echo agent."""

from __future__ import annotations

import pytest

from mist_tui.broker_client import BrokerClient


@pytest.mark.asyncio
async def test_request_catalog(echo_agent):
    """Catalog includes the echo agent."""
    agent_id, socket_path = echo_agent
    bc = BrokerClient(socket_path)
    await bc.connect()
    try:
        catalog = await bc.request_catalog()
        assert len(catalog) >= 1
        names = [a["name"] for a in catalog]
        assert "echo" in names
    finally:
        await bc.close()


@pytest.mark.asyncio
async def test_send_command(echo_agent):
    """send_command returns echo response text."""
    agent_id, socket_path = echo_agent
    bc = BrokerClient(socket_path)
    await bc.connect()
    try:
        result = await bc.send_command(agent_id, "hello world")
        assert result == "echo: hello world"
    finally:
        await bc.close()


@pytest.mark.asyncio
async def test_send_command_multiple(echo_agent):
    """Multiple sequential commands work correctly."""
    agent_id, socket_path = echo_agent
    bc = BrokerClient(socket_path)
    await bc.connect()
    try:
        r1 = await bc.send_command(agent_id, "first")
        r2 = await bc.send_command(agent_id, "second")
        assert r1 == "echo: first"
        assert r2 == "echo: second"
    finally:
        await bc.close()


@pytest.mark.asyncio
async def test_request_service_tasks(echo_agent):
    """Service request round-trip for task creation and listing."""
    _, socket_path = echo_agent
    bc = BrokerClient(socket_path)
    await bc.connect()
    try:
        # Create a task
        result = await bc.request_service(
            "tasks", "create",
            {"title": "test task"},
        )
        assert "task_id" in result

        # List tasks
        tasks = await bc.request_service("tasks", "list")
        assert isinstance(tasks, list)
        assert len(tasks) >= 1
        assert any(t["title"] == "test task" for t in tasks)
    finally:
        await bc.close()


@pytest.mark.asyncio
async def test_close_cleans_up(echo_agent):
    """Closing the client cancels the reader and clears state."""
    _, socket_path = echo_agent
    bc = BrokerClient(socket_path)
    await bc.connect()
    assert bc._reader_task is not None
    assert not bc._reader_task.done()

    await bc.close()
    assert bc._reader_task is None
    assert len(bc._pending) == 0
    assert len(bc._streams) == 0
