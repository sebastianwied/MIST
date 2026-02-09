"""Tests for mist_client.client — mock broker, verify service request format."""

from __future__ import annotations

import asyncio
import json

import pytest

from mist_client.client import BrokerClient
from mist_client.protocol import (
    Message,
    decode_message,
    encode_message,
    MSG_COMMAND,
    MSG_RESPONSE,
    MSG_SERVICE_REQUEST,
    MSG_SERVICE_RESPONSE,
    MSG_SERVICE_ERROR,
    RESP_TEXT,
    RESP_TABLE,
    RESP_ERROR,
)


class MockBroker:
    """A mock broker that echoes service requests back as responses."""

    def __init__(self, sock_path):
        self.sock_path = sock_path
        self.received: list[Message] = []
        self._server = None

    async def start(self):
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.sock_path),
        )

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_client(self, reader, writer):
        try:
            while True:
                try:
                    raw = await reader.readuntil(b"\n")
                except (asyncio.IncompleteReadError, ConnectionResetError):
                    break
                if not raw:
                    break
                msg = decode_message(raw.decode().rstrip("\n"))
                self.received.append(msg)

                if msg.type == MSG_SERVICE_REQUEST:
                    reply = Message.reply(
                        msg, "broker", MSG_SERVICE_RESPONSE,
                        {"result": msg.payload},
                    )
                    writer.write((encode_message(reply) + "\n").encode())
                    await writer.drain()
        except asyncio.CancelledError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()


@pytest.fixture
def sock_path(tmp_path):
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        yield Path(td) / "test.sock"


@pytest.fixture
async def mock_broker(sock_path):
    broker = MockBroker(sock_path)
    await broker.start()
    yield broker
    await broker.stop()


@pytest.fixture
async def client(mock_broker, sock_path):
    c = BrokerClient("test-agent", sock_path)
    await c.connect()
    yield c
    await c.close()


class TestServiceRequests:
    async def test_save_raw_input(self, client, mock_broker):
        result = await client.save_raw_input("hello world")
        # Mock broker echoes the payload back as result
        assert result["service"] == "storage"
        assert result["action"] == "save_raw_input"
        assert result["params"]["text"] == "hello world"

    async def test_list_tasks(self, client, mock_broker):
        result = await client.list_tasks()
        assert result["service"] == "tasks"
        assert result["action"] == "list"

    async def test_create_task(self, client, mock_broker):
        result = await client.create_task("Buy milk", due_date="2024-12-31")
        assert result["service"] == "tasks"
        assert result["params"]["title"] == "Buy milk"
        assert result["params"]["due_date"] == "2024-12-31"

    async def test_llm_chat(self, client, mock_broker):
        result = await client.llm_chat("hello", system="Be helpful")
        assert result["service"] == "llm"
        assert result["action"] == "chat"
        assert result["params"]["prompt"] == "hello"
        assert result["params"]["system"] == "Be helpful"

    async def test_get_setting(self, client, mock_broker):
        result = await client.get_setting("model")
        assert result["service"] == "settings"
        assert result["params"]["key"] == "model"

    async def test_add_topic(self, client, mock_broker):
        result = await client.add_topic("ML", "ml")
        assert result["params"]["name"] == "ML"
        assert result["params"]["slug"] == "ml"


class TestServiceError:
    async def test_error_raises(self, sock_path):
        """When broker replies with service.error, client raises RuntimeError."""
        async def error_handler(reader, writer):
            try:
                raw = await reader.readuntil(b"\n")
                msg = decode_message(raw.decode().rstrip("\n"))
                reply = Message.reply(
                    msg, "broker", MSG_SERVICE_ERROR,
                    {"error": "something went wrong"},
                )
                writer.write((encode_message(reply) + "\n").encode())
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(error_handler, path=str(sock_path))
        try:
            client = BrokerClient("test", sock_path)
            await client.connect()
            try:
                with pytest.raises(RuntimeError, match="something went wrong"):
                    await client.list_tasks()
            finally:
                await client.close()
        finally:
            server.close()
            await server.wait_closed()


class TestStructuredResponses:
    async def test_respond_text_format(self, mock_broker, sock_path):
        """Verify the wire format of respond_text."""
        # We need a raw connection to capture what the client sends
        sent_messages = []

        async def capture_handler(reader, writer):
            try:
                while True:
                    raw = await reader.readuntil(b"\n")
                    if not raw:
                        break
                    msg = decode_message(raw.decode().rstrip("\n"))
                    sent_messages.append(msg)
            except (asyncio.IncompleteReadError, ConnectionResetError, asyncio.CancelledError):
                pass
            finally:
                writer.close()
                await writer.wait_closed()

        await mock_broker.stop()
        server = await asyncio.start_unix_server(capture_handler, path=str(sock_path))
        try:
            client = BrokerClient("notes-0", sock_path)
            await client.connect()
            try:
                original = Message.create(MSG_COMMAND, "ui", "notes-0", {"text": "hello"})
                await client.respond_text(original, "Reply text", format="markdown")
                # Give it a moment to flush
                await asyncio.sleep(0.05)

                assert len(sent_messages) == 1
                resp = sent_messages[0]
                assert resp.type == MSG_RESPONSE
                assert resp.payload["type"] == RESP_TEXT
                assert resp.payload["content"]["text"] == "Reply text"
                assert resp.payload["content"]["format"] == "markdown"
                assert resp.reply_to == original.id
                assert resp.to == "ui"
            finally:
                await client.close()
        finally:
            server.close()
            await server.wait_closed()
