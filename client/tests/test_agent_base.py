"""Tests for mist_client.agent — register, receive command, send response."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from mist_client.agent import AgentBase
from mist_client.protocol import (
    Message,
    decode_message,
    encode_message,
    MSG_AGENT_REGISTER,
    MSG_AGENT_READY,
    MSG_COMMAND,
    MSG_RESPONSE,
    MSG_AGENT_DISCONNECT,
    RESP_TEXT,
)


@pytest.fixture
def sock_path():
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        yield Path(td) / "test.sock"


class EchoAgent(AgentBase):
    """Test agent that echoes commands back."""

    def manifest(self):
        return {
            "name": "echo",
            "description": "Echo agent for testing",
            "commands": [{"name": "echo", "description": "Echo back"}],
            "panels": [],
        }

    async def handle_command(self, msg):
        text = msg.payload.get("text", "")
        await self.client.respond_text(msg, f"echo: {text}")


async def test_agent_registers_and_handles_command(sock_path):
    """Full lifecycle: agent connects, registers, receives command, responds."""

    received_register = []
    received_responses = []

    async def mock_broker(reader, writer):
        try:
            # 1. Receive registration
            raw = await reader.readuntil(b"\n")
            reg = decode_message(raw.decode().rstrip("\n"))
            received_register.append(reg)
            assert reg.type == MSG_AGENT_REGISTER
            assert reg.payload["name"] == "echo"

            # 2. Send ready
            ready = Message.reply(
                reg, "broker", MSG_AGENT_READY,
                {"agent_id": "echo-0"},
            )
            writer.write((encode_message(ready) + "\n").encode())
            await writer.drain()

            # 3. Send a command to the agent
            cmd = Message.create(
                MSG_COMMAND, "ui", "echo-0",
                {"text": "hello"},
            )
            writer.write((encode_message(cmd) + "\n").encode())
            await writer.drain()

            # 4. Receive the response
            raw = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=5.0)
            resp = decode_message(raw.decode().rstrip("\n"))
            received_responses.append(resp)

            # 5. Wait for disconnect (when we cancel the agent)
            try:
                raw = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=2.0)
                disc = decode_message(raw.decode().rstrip("\n"))
                assert disc.type == MSG_AGENT_DISCONNECT
            except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                pass
        except asyncio.CancelledError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(mock_broker, path=str(sock_path))
    try:
        agent = EchoAgent(socket_path=sock_path)
        agent_task = asyncio.create_task(agent.run())

        # Wait for the response to arrive
        for _ in range(50):
            if received_responses:
                break
            await asyncio.sleep(0.05)

        assert len(received_responses) == 1
        resp = received_responses[0]
        assert resp.type == MSG_RESPONSE
        assert resp.payload["type"] == RESP_TEXT
        assert resp.payload["content"]["text"] == "echo: hello"

        # Clean up
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
    finally:
        server.close()
        await server.wait_closed()


async def test_agent_manifest_not_implemented(sock_path):
    """AgentBase without overrides raises NotImplementedError."""
    agent = AgentBase(socket_path=sock_path)
    with pytest.raises(NotImplementedError):
        agent.manifest()
