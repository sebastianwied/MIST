"""High-level async broker client for TUI widgets."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from mist_core.protocol import (
    Message,
    MSG_AGENT_CATALOG,
    MSG_AGENT_LIST,
    MSG_COMMAND,
    MSG_ERROR,
    MSG_RESPONSE,
    MSG_RESPONSE_CHUNK,
    MSG_RESPONSE_END,
    MSG_SERVICE_ERROR,
    MSG_SERVICE_REQUEST,
    MSG_SERVICE_RESPONSE,
)
from mist_core.transport import Client, DEFAULT_SOCKET_PATH

log = logging.getLogger(__name__)

_RESPONSE_TYPES = frozenset({
    MSG_RESPONSE,
    MSG_AGENT_CATALOG,
    MSG_SERVICE_RESPONSE,
    MSG_SERVICE_ERROR,
    MSG_ERROR,
})

_STREAM_TYPES = frozenset({MSG_RESPONSE_CHUNK, MSG_RESPONSE_END})


class BrokerClient:
    """Async broker client with background message reader.

    Each instance owns a separate socket connection.  A background
    ``asyncio.Task`` reads all incoming messages and dispatches them to
    waiting ``Future``s (single-response) or ``Queue``s (streaming).
    """

    def __init__(self, socket_path: Path | str = DEFAULT_SOCKET_PATH) -> None:
        self._client = Client(path=socket_path)
        self._client_id = f"tui-{uuid.uuid4().hex[:8]}"
        self._pending: dict[str, asyncio.Future[Message]] = {}
        self._streams: dict[str, asyncio.Queue[Message]] = {}
        self._reader_task: asyncio.Task[None] | None = None

    @property
    def client_id(self) -> str:
        return self._client_id

    # ── lifecycle ────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Connect to broker and start the background reader."""
        await self._client.connect()
        self._reader_task = asyncio.create_task(
            self._read_loop(), name=f"reader-{self._client_id}"
        )

    async def close(self) -> None:
        """Cancel reader and close transport."""
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        # Fail any pending futures
        for fut in self._pending.values():
            if not fut.done():
                fut.cancel()
        self._pending.clear()
        self._streams.clear()
        self._client.close()
        await self._client.wait_closed()

    # ── public API ───────────────────────────────────────────────────

    async def request_catalog(self, timeout: float = 5.0) -> list[dict[str, Any]]:
        """Ask the broker for the agent catalog."""
        msg = Message.create(
            MSG_AGENT_LIST, self._client_id, "broker",
        )
        reply = await self._request(msg, timeout)
        return reply.payload.get("agents", [])

    async def send_command(
        self, agent_id: str, text: str, timeout: float = 30.0,
    ) -> str:
        """Send a command to *agent_id* and wait for the full response."""
        msg = Message.create(
            MSG_COMMAND, self._client_id, agent_id,
            payload={"text": text},
        )
        reply = await self._request(msg, timeout)
        if reply.type == MSG_ERROR:
            raise RuntimeError(reply.payload.get("error", "unknown error"))
        return reply.payload.get("text", "")

    async def send_command_stream(
        self, agent_id: str, text: str,
    ) -> AsyncIterator[str]:
        """Send a command and yield response chunks until done."""
        msg = Message.create(
            MSG_COMMAND, self._client_id, agent_id,
            payload={"text": text},
        )
        queue: asyncio.Queue[Message] = asyncio.Queue()
        self._streams[msg.id] = queue
        try:
            await self._client.send(msg)
            while True:
                chunk_msg = await queue.get()
                if chunk_msg.type == MSG_RESPONSE_END:
                    break
                if chunk_msg.type == MSG_ERROR:
                    raise RuntimeError(
                        chunk_msg.payload.get("error", "unknown error")
                    )
                yield chunk_msg.payload.get("text", "")
        finally:
            self._streams.pop(msg.id, None)

    async def request_service(
        self,
        service: str,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> Any:
        """Send a service request and return the result."""
        msg = Message.create(
            MSG_SERVICE_REQUEST, self._client_id, "broker",
            payload={
                "service": service,
                "action": action,
                "params": params or {},
            },
        )
        reply = await self._request(msg, timeout)
        if reply.type == MSG_SERVICE_ERROR:
            raise RuntimeError(reply.payload.get("error", "service error"))
        return reply.payload.get("result")

    # ── internals ────────────────────────────────────────────────────

    async def _request(self, msg: Message, timeout: float) -> Message:
        """Send *msg*, register a Future, and await the reply."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Message] = loop.create_future()
        self._pending[msg.id] = fut
        try:
            await self._client.send(msg)
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"no reply to {msg.type} ({msg.id}) within {timeout}s"
            )
        finally:
            self._pending.pop(msg.id, None)

    async def _read_loop(self) -> None:
        """Background task: read messages and dispatch to waiters."""
        try:
            async for msg in self._client:
                self._dispatch_incoming(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("reader loop error")
        finally:
            # Fail all pending futures on disconnect
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("broker disconnected"))
            self._pending.clear()

    def _dispatch_incoming(self, msg: Message) -> None:
        """Route an incoming message to the correct Future or Queue."""
        key = msg.reply_to
        if key is None:
            log.debug("ignoring message without reply_to: %s", msg.type)
            return

        # Streaming messages go to queues
        if msg.type in _STREAM_TYPES:
            queue = self._streams.get(key)
            if queue is not None:
                queue.put_nowait(msg)
            else:
                log.debug("no stream for reply_to=%s", key)
            return

        # Single-response or error messages go to futures
        # Also route response.end and errors to streams if present
        if key in self._streams:
            self._streams[key].put_nowait(msg)
            return

        fut = self._pending.get(key)
        if fut is not None and not fut.done():
            fut.set_result(msg)
        else:
            log.debug("no waiter for reply_to=%s (%s)", key, msg.type)
