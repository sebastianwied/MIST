"""Tests for mist_core.transport — Unix socket and WebSocket."""

import asyncio
import tempfile
from pathlib import Path

import pytest
import websockets

from mist_core.protocol import (
    Message,
    MSG_COMMAND,
    MSG_RESPONSE,
    MSG_ERROR,
    decode_message,
    encode_message,
)
from mist_core.transport import Client, Connection, Server, WebSocketServer, WebSocketConnection


async def _echo_handler(msg: Message, conn) -> None:
    """Reply with the same payload."""
    reply = Message.reply(msg, sender="echo-server", type=MSG_RESPONSE, payload=msg.payload)
    await conn.send(reply)


@pytest.fixture
def sock_path():
    with tempfile.TemporaryDirectory(dir="/tmp") as td:
        yield Path(td) / "t.sock"


# ── Unix socket tests ───────────────────────────────────────────────


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
        finally:
            client.close()
            await client.wait_closed()
    finally:
        await server.stop()


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


async def test_client_disconnect(sock_path):
    server = Server(_echo_handler, path=sock_path)
    await server.start()
    try:
        c1 = Client(path=sock_path)
        await c1.connect()
        c1.close()
        await c1.wait_closed()
        await asyncio.sleep(0.05)

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


async def test_malformed_message_error_frame(sock_path):
    server = Server(_echo_handler, path=sock_path)
    await server.start()
    try:
        reader, writer = await asyncio.open_unix_connection(str(sock_path))
        try:
            writer.write(b'{"bad": "data"}\n')
            await writer.drain()
            raw = await asyncio.wait_for(reader.readuntil(b"\n"), timeout=2.0)
            err = decode_message(raw.decode().rstrip("\n"))
            assert err.type == MSG_ERROR
            assert "error" in err.payload
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.stop()


# ── WebSocket tests ─────────────────────────────────────────────────


async def test_websocket_echo_round_trip():
    ws_server = WebSocketServer(_echo_handler, host="127.0.0.1", port=0)
    # Start on a random port to avoid conflicts
    import websockets as ws_lib

    received = []

    async def ws_handler(websocket):
        conn = WebSocketConnection(websocket)
        async for raw in websocket:
            if isinstance(raw, bytes):
                raw = raw.decode()
            msg = decode_message(raw)
            reply = Message.reply(msg, sender="echo-server", type=MSG_RESPONSE, payload=msg.payload)
            await conn.send(reply)

    async with ws_lib.serve(ws_handler, "127.0.0.1", 0) as server:
        # Get the actual port
        port = server.sockets[0].getsockname()[1]

        async with ws_lib.connect(f"ws://127.0.0.1:{port}") as ws:
            msg = Message.create(MSG_COMMAND, sender="ui", to="echo-server", payload={"x": 42})
            await ws.send(encode_message(msg))
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            reply = decode_message(raw)
            assert reply.type == MSG_RESPONSE
            assert reply.payload == {"x": 42}
            assert reply.reply_to == msg.id
