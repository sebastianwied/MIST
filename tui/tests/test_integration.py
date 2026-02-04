"""Full-stack integration tests: broker + echo agent + BrokerClient."""

from __future__ import annotations

import pytest

from mist_tui.broker_client import BrokerClient


@pytest.mark.asyncio
async def test_full_stack_catalog(echo_agent):
    """BrokerClient connects and retrieves catalog with echo agent."""
    agent_id, socket_path = echo_agent
    bc = BrokerClient(socket_path)
    await bc.connect()
    try:
        catalog = await bc.request_catalog()
        agent_ids = [a["agent_id"] for a in catalog]
        assert agent_id in agent_ids
    finally:
        await bc.close()


@pytest.mark.asyncio
async def test_full_stack_command(echo_agent):
    """BrokerClient sends command and receives echo response."""
    agent_id, socket_path = echo_agent
    bc = BrokerClient(socket_path)
    await bc.connect()
    try:
        result = await bc.send_command(agent_id, "integration test")
        assert result == "echo: integration test"
    finally:
        await bc.close()


@pytest.mark.asyncio
async def test_full_stack_service_round_trip(echo_agent):
    """BrokerClient service request round-trip: create and list tasks."""
    _, socket_path = echo_agent
    bc = BrokerClient(socket_path)
    await bc.connect()
    try:
        # Create
        created = await bc.request_service(
            "tasks", "create",
            {"title": "integration task"},
        )
        assert "task_id" in created

        # List
        tasks = await bc.request_service("tasks", "list")
        assert any(t["title"] == "integration task" for t in tasks)
    finally:
        await bc.close()


@pytest.mark.asyncio
async def test_full_stack_multiple_clients(echo_agent):
    """Multiple BrokerClients can communicate independently."""
    agent_id, socket_path = echo_agent
    bc1 = BrokerClient(socket_path)
    bc2 = BrokerClient(socket_path)
    await bc1.connect()
    await bc2.connect()
    try:
        r1 = await bc1.send_command(agent_id, "from client 1")
        r2 = await bc2.send_command(agent_id, "from client 2")
        assert r1 == "echo: from client 1"
        assert r2 == "echo: from client 2"
    finally:
        await bc1.close()
        await bc2.close()
