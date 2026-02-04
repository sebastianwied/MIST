"""Tests for mist_core.transport."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from mist_core.protocol import (
    Message,
    MSG_COMMAND,
    MSG_RESPONSE,
    MSG_ERROR,
    decode_message,
)
from mist_core.transport import Client, Connection, Server


async def _echo_handler(msg: Message, conn: Connection) -> None:
    """Reply with the same payload."""
    reply = Message.reply(msg, sender="echo-server", type=MSG_RESPONSE, payload=msg.payload)
    await conn.send(reply)


@pytest.fixture
def sock_path():
    # Use /tmp directly to avoid AF_UNIX path length limit (104 bytes on macOS)
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        yield Path(td) / "t.sock"


# ── Echo round-trip ─────────────────────────────────────────────────


async def test_echo_round_trip(sock_path):
    server = Server(_echo_handler, path=sock_path)
    await server.start()
    try:
        client = Client(path=sock_path)
        await client.connect()
        try:
            msg = Message.create(MSG_COMMAND, sender="test", to="echo-server", payload={"n": 1})
            reply = await client.request(msg, timeout=2.0)
            assert reply.type == MSG_RESPONSE
            assert reply.payload == {"n": 1}
            assert reply.reply_to == msg.id
            assert reply.to == "test"
        finally:
            client.close()
            await client.wait_closed()
    finally:
        await server.stop()


# ── Multiple messages on one connection ─────────────────────────────


async def test_multiple_messages(sock_path):
    server = Server(_echo_handler, path=sock_path)
    await server.start()
    try:
        client = Client(path=sock_path)
        await client.connect()
        try:
            for i in range(5):
                msg = Message.create(
                    MSG_COMMAND, sender="test", to="echo-server", payload={"i": i}
                )
                reply = await client.request(msg, timeout=2.0)
                assert reply.payload == {"i": i}
        finally:
            client.close()
            await client.wait_closed()
    finally:
        await server.stop()


# ── Multiple concurrent clients ─────────────────────────────────────


async def test_concurrent_clients(sock_path):
    server = Server(_echo_handler, path=sock_path)
    await server.start()
    try:

        async def run_client(client_id: int) -> list[dict]:
            client = Client(path=sock_path)
            await client.connect()
            results = []
            try:
                for j in range(3):
                    msg = Message.create(
                        MSG_COMMAND,
                        sender=f"client-{client_id}",
                        to="echo-server",
                        payload={"client": client_id, "seq": j},
                    )
                    reply = await client.request(msg, timeout=2.0)
                    results.append(reply.payload)
            finally:
                client.close()
                await client.wait_closed()
            return results

        results = await asyncio.gather(run_client(0), run_client(1), run_client(2))
        for client_id, payloads in enumerate(results):
            assert len(payloads) == 3
            for j, p in enumerate(payloads):
                assert p == {"client": client_id, "seq": j}
    finally:
        await server.stop()


# ── Client disconnect doesn't crash server ──────────────────────────


async def test_client_disconnect(sock_path):
    server = Server(_echo_handler, path=sock_path)
    await server.start()
    try:
        # First client connects and disconnects abruptly
        c1 = Client(path=sock_path)
        await c1.connect()
        c1.close()
        await c1.wait_closed()

        # Give the server a moment to process the disconnect
        await asyncio.sleep(0.05)

        # Second client should still work fine
        c2 = Client(path=sock_path)
        await c2.connect()
        try:
            msg = Message.create(MSG_COMMAND, sender="c2", to="echo-server", payload={"ok": True})
            reply = await c2.request(msg, timeout=2.0)
            assert reply.payload == {"ok": True}
        finally:
            c2.close()
            await c2.wait_closed()
    finally:
        await server.stop()


# ── Malformed message gets error frame ──────────────────────────────


async def test_malformed_message_error_frame(sock_path):
    server = Server(_echo_handler, path=sock_path)
    await server.start()
    try:
        reader, writer = await asyncio.open_unix_connection(str(sock_path))
        try:
            # Send garbage
            writer.write(b'{"bad": "data"}\n')
            await writer.drain()

            # Should get an error frame back
            raw = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=2.0)
            err = decode_message(raw.decode().rstrip("\n"))
            assert err.type == MSG_ERROR
            assert "error" in err.payload

            # Server still works: send a valid message
            valid = Message.create(MSG_COMMAND, sender="test", to="echo-server", payload={"after": "error"})
            from mist_core.protocol import encode_message

            writer.write((encode_message(valid) + "\n").encode())
            await writer.drain()
            raw2 = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=2.0)
            reply = decode_message(raw2.decode().rstrip("\n"))
            assert reply.type == MSG_RESPONSE
            assert reply.payload == {"after": "error"}
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()
