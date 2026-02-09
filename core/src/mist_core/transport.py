"""Async Unix-socket and WebSocket transport for MIST messages."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Awaitable, Callable

import websockets
from websockets.asyncio.server import Server as WsServer, ServerConnection

from .protocol import (
    Message,
    ProtocolError,
    decode_message,
    encode_message,
    MSG_ERROR,
)

log = logging.getLogger(__name__)

Handler = Callable[[Message, "Connection"], Awaitable[None]]


# ── Connection ──────────────────────────────────────────────────────


class Connection:
    """Wraps an asyncio stream pair for sending messages."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer

    async def send(self, msg: Message) -> None:
        line = encode_message(msg) + "\n"
        self._writer.write(line.encode())
        await self._writer.drain()

    async def recv(self) -> Message | None:
        try:
            raw = await self._reader.readuntil(b"\n")
        except (asyncio.IncompleteReadError, ConnectionResetError):
            return None
        if not raw:
            return None
        return decode_message(raw.decode().rstrip("\n"))

    def close(self) -> None:
        self._writer.close()

    async def wait_closed(self) -> None:
        await self._writer.wait_closed()


# ── Unix Socket Server ──────────────────────────────────────────────


class Server:
    """Unix-socket server that dispatches incoming messages to *handler*."""

    def __init__(self, handler: Handler, path: Path | str) -> None:
        self._handler = handler
        self._path = Path(path)
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            self._path.unlink()
        self._server = await asyncio.start_unix_server(
            self._client_connected,
            path=str(self._path),
        )
        log.info("Unix socket listening on %s", self._path)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._path.exists():
            self._path.unlink()

    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("call start() first")
        await self._server.serve_forever()

    async def _client_connected(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        conn = Connection(reader, writer)
        try:
            while True:
                try:
                    raw = await reader.readuntil(b"\n")
                except (asyncio.IncompleteReadError, ConnectionResetError):
                    break
                if not raw:
                    break

                line = raw.decode().rstrip("\n")
                try:
                    msg = decode_message(line)
                except ProtocolError as exc:
                    log.warning("malformed message: %s", exc)
                    err = Message.create(
                        type=MSG_ERROR,
                        sender="server",
                        to="unknown",
                        payload={"error": str(exc)},
                    )
                    await conn.send(err)
                    continue

                try:
                    await self._handler(msg, conn)
                except Exception:
                    log.exception("handler error for %s", msg.type)
        finally:
            conn.close()
            await conn.wait_closed()


# ── Unix Socket Client ──────────────────────────────────────────────


class Client:
    """Unix-socket client for sending and receiving messages."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._conn: Connection | None = None

    async def connect(self) -> None:
        reader, writer = await asyncio.open_unix_connection(str(self._path))
        self._conn = Connection(reader, writer)

    def _require_conn(self) -> Connection:
        if self._conn is None:
            raise RuntimeError("call connect() first")
        return self._conn

    async def send(self, msg: Message) -> None:
        await self._require_conn().send(msg)

    async def recv(self) -> Message | None:
        return await self._require_conn().recv()

    async def request(self, msg: Message, timeout: float = 5.0) -> Message:
        """Send *msg* and wait for a reply whose ``reply_to`` matches."""
        conn = self._require_conn()
        await conn.send(msg)
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"no reply to {msg.id} within {timeout}s")
            reply = await asyncio.wait_for(conn.recv(), timeout=remaining)
            if reply is None:
                raise ConnectionError("server closed connection")
            if reply.reply_to == msg.id:
                return reply

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()

    async def wait_closed(self) -> None:
        if self._conn is not None:
            await self._conn.wait_closed()

    def __aiter__(self) -> Client:
        return self

    async def __anext__(self) -> Message:
        msg = await self._require_conn().recv()
        if msg is None:
            raise StopAsyncIteration
        return msg


# ── WebSocket Connection ────────────────────────────────────────────


class WebSocketConnection:
    """Wraps a websockets connection for sending/receiving Messages."""

    def __init__(self, ws: ServerConnection) -> None:
        self._ws = ws

    async def send(self, msg: Message) -> None:
        await self._ws.send(encode_message(msg))

    async def recv(self) -> Message | None:
        try:
            raw = await self._ws.recv()
            if isinstance(raw, bytes):
                raw = raw.decode()
            return decode_message(raw)
        except (websockets.exceptions.ConnectionClosed, ProtocolError):
            return None

    async def close(self) -> None:
        await self._ws.close()


# ── WebSocket Server ────────────────────────────────────────────────

WebSocketHandler = Callable[[Message, WebSocketConnection], Awaitable[None]]


class WebSocketServer:
    """WebSocket server for UI connections."""

    def __init__(
        self,
        handler: WebSocketHandler,
        host: str = "127.0.0.1",
        port: int = 8765,
    ) -> None:
        self._handler = handler
        self._host = host
        self._port = port
        self._server: WsServer | None = None

    async def start(self) -> None:
        self._server = await websockets.serve(
            self._ws_handler,
            self._host,
            self._port,
        )
        log.info("WebSocket listening on ws://%s:%d", self._host, self._port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("call start() first")
        await self._server.serve_forever()

    async def _ws_handler(self, ws: ServerConnection) -> None:
        conn = WebSocketConnection(ws)
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    raw = raw.decode()
                try:
                    msg = decode_message(raw)
                except ProtocolError as exc:
                    log.warning("malformed WebSocket message: %s", exc)
                    err = Message.create(
                        type=MSG_ERROR,
                        sender="server",
                        to="unknown",
                        payload={"error": str(exc)},
                    )
                    await conn.send(err)
                    continue

                try:
                    await self._handler(msg, conn)
                except Exception:
                    log.exception("WebSocket handler error for %s", msg.type)
        except websockets.exceptions.ConnectionClosed:
            pass
