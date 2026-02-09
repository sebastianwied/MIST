"""BrokerClient — the main agent API for interacting with the MIST broker."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .protocol import (
    Message,
    decode_message,
    encode_message,
    MSG_COMMAND,
    MSG_RESPONSE,
    MSG_SERVICE_REQUEST,
    MSG_SERVICE_RESPONSE,
    MSG_SERVICE_ERROR,
    MSG_AGENT_MESSAGE,
    RESP_TEXT,
    RESP_TABLE,
    RESP_LIST,
    RESP_EDITOR,
    RESP_CONFIRM,
    RESP_ERROR,
    RESP_PROGRESS,
)


class BrokerClient:
    """Agent-side client for communicating with the MIST broker.

    Provides methods for:
    - Storage operations (namespaced by broker automatically)
    - LLM requests (queued by core)
    - Structured responses
    - Inter-agent messaging
    - Settings
    """

    def __init__(self, agent_id: str, socket_path: Path | str) -> None:
        self.agent_id = agent_id
        self._socket_path = Path(socket_path)
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[str, asyncio.Future[Message]] = {}
        self._command_queue: asyncio.Queue[Message] = asyncio.Queue()
        self._listen_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Connect to the broker's Unix socket."""
        self._reader, self._writer = await asyncio.open_unix_connection(
            str(self._socket_path)
        )
        self._listen_task = asyncio.create_task(self._listen_loop())

    async def close(self) -> None:
        """Disconnect from the broker."""
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    async def _send(self, msg: Message) -> None:
        if self._writer is None:
            raise RuntimeError("not connected")
        line = encode_message(msg) + "\n"
        self._writer.write(line.encode())
        await self._writer.drain()

    async def _listen_loop(self) -> None:
        """Read messages from the broker, dispatching replies and commands."""
        assert self._reader is not None
        try:
            while True:
                try:
                    raw = await self._reader.readuntil(b"\n")
                except (asyncio.IncompleteReadError, ConnectionResetError):
                    break
                if not raw:
                    break
                msg = decode_message(raw.decode().rstrip("\n"))

                # Route reply to pending future
                if msg.reply_to and msg.reply_to in self._pending:
                    future = self._pending.pop(msg.reply_to)
                    if not future.done():
                        future.set_result(msg)
                elif msg.type == MSG_COMMAND:
                    await self._command_queue.put(msg)
                elif msg.type == MSG_AGENT_MESSAGE:
                    await self._command_queue.put(msg)
        except asyncio.CancelledError:
            pass

    async def _request(self, msg: Message, timeout: float = 30.0) -> Message:
        """Send a message and wait for the reply."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Message] = loop.create_future()
        self._pending[msg.id] = future
        await self._send(msg)
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(msg.id, None)
            raise

    async def recv_command(self) -> Message:
        """Wait for the next command from the broker."""
        return await self._command_queue.get()

    # ── Service request helper ──────────────────────────────────────

    async def _service_request(
        self,
        service: str,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> Any:
        """Send a service.request and return the result."""
        msg = Message.create(
            MSG_SERVICE_REQUEST,
            sender=self.agent_id,
            to="broker",
            payload={
                "service": service,
                "action": action,
                "params": params or {},
            },
        )
        reply = await self._request(msg, timeout=timeout)
        if reply.type == MSG_SERVICE_ERROR:
            raise RuntimeError(reply.payload.get("error", "unknown service error"))
        return reply.payload.get("result")

    # ── Storage (namespaced by broker) ──────────────────────────────

    async def save_raw_input(self, text: str, source: str = "terminal") -> bool:
        return await self._service_request(
            "storage", "save_raw_input", {"text": text, "source": source},
        )

    async def parse_buffer(self) -> list[dict]:
        return await self._service_request("storage", "parse_buffer")

    async def clear_buffer(self) -> bool:
        return await self._service_request("storage", "clear_buffer")

    async def load_topic_index(self) -> list[dict]:
        return await self._service_request("storage", "load_topic_index")

    async def add_topic(self, name: str, slug: str) -> dict:
        return await self._service_request(
            "storage", "add_topic", {"name": name, "slug": slug},
        )

    async def find_topic(self, identifier: str) -> dict | None:
        return await self._service_request(
            "storage", "find_topic", {"identifier": identifier},
        )

    async def load_topic_buffer(self, slug: str) -> list[dict]:
        return await self._service_request(
            "storage", "load_topic_buffer", {"slug": slug},
        )

    async def append_to_topic_buffer(self, slug: str, entries: list[dict]) -> bool:
        return await self._service_request(
            "storage", "append_to_topic_buffer",
            {"slug": slug, "entries": entries},
        )

    async def load_topic_note_feed(self, slug: str) -> str:
        return await self._service_request(
            "storage", "load_topic_note_feed", {"slug": slug},
        )

    async def save_topic_note_feed(self, slug: str, content: str) -> bool:
        return await self._service_request(
            "storage", "save_topic_note_feed", {"slug": slug, "content": content},
        )

    async def load_topic_synthesis(self, slug: str) -> str:
        return await self._service_request(
            "storage", "load_topic_synthesis", {"slug": slug},
        )

    async def save_topic_synthesis(self, slug: str, content: str) -> bool:
        return await self._service_request(
            "storage", "save_topic_synthesis", {"slug": slug, "content": content},
        )

    async def list_drafts(self) -> list[str]:
        return await self._service_request("storage", "list_drafts")

    async def create_draft(self, title: str) -> dict:
        return await self._service_request(
            "storage", "create_draft", {"title": title},
        )

    async def load_draft(self, filename: str) -> str:
        return await self._service_request(
            "storage", "load_draft", {"filename": filename},
        )

    async def save_draft(self, filename: str, content: str) -> bool:
        return await self._service_request(
            "storage", "save_draft", {"filename": filename, "content": content},
        )

    async def merge_topics(self, source_slug: str, target_slug: str) -> dict:
        return await self._service_request(
            "storage", "merge_topics",
            {"source_slug": source_slug, "target_slug": target_slug},
        )

    async def get_last_aggregate_time(self) -> str | None:
        return await self._service_request("storage", "get_last_aggregate_time")

    async def set_last_aggregate_time(self, ts: str) -> bool:
        return await self._service_request(
            "storage", "set_last_aggregate_time", {"ts": ts},
        )

    async def get_last_sync_time(self) -> str | None:
        return await self._service_request("storage", "get_last_sync_time")

    async def set_last_sync_time(self, ts: str) -> bool:
        return await self._service_request(
            "storage", "set_last_sync_time", {"ts": ts},
        )

    # ── Tasks (shared/global) ───────────────────────────────────────

    async def create_task(self, title: str, due_date: str | None = None) -> dict:
        params: dict[str, Any] = {"title": title}
        if due_date:
            params["due_date"] = due_date
        return await self._service_request("tasks", "create", params)

    async def list_tasks(self, include_done: bool = False) -> list[dict]:
        return await self._service_request(
            "tasks", "list", {"include_done": include_done},
        )

    async def get_task(self, task_id: int) -> dict | None:
        return await self._service_request("tasks", "get", {"task_id": task_id})

    async def update_task(self, task_id: int, **fields) -> bool:
        return await self._service_request(
            "tasks", "update", {"task_id": task_id, **fields},
        )

    async def delete_task(self, task_id: int) -> bool:
        return await self._service_request("tasks", "delete", {"task_id": task_id})

    async def get_upcoming_tasks(self, days: int = 7) -> list[dict]:
        return await self._service_request("tasks", "upcoming", {"days": days})

    # ── Events (shared/global) ──────────────────────────────────────

    async def create_event(self, title: str, start_time: str, **kwargs) -> dict:
        return await self._service_request(
            "events", "create", {"title": title, "start_time": start_time, **kwargs},
        )

    async def list_events(self) -> list[dict]:
        return await self._service_request("events", "list")

    async def get_upcoming_events(self, days: int = 7) -> list[dict]:
        return await self._service_request("events", "upcoming", {"days": days})

    # ── Articles (shared/global) ────────────────────────────────────

    async def create_article(self, title: str, authors: list[str], **kwargs) -> dict:
        return await self._service_request(
            "articles", "create", {"title": title, "authors": authors, **kwargs},
        )

    async def list_articles(self, tag: str | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if tag:
            params["tag"] = tag
        return await self._service_request("articles", "list", params)

    async def get_article(self, article_id: int) -> dict | None:
        return await self._service_request(
            "articles", "get", {"article_id": article_id},
        )

    # ── LLM (queued by core) ────────────────────────────────────────

    async def llm_chat(
        self,
        prompt: str,
        model: str | None = None,
        command: str | None = None,
        temperature: float = 0.3,
        system: str | None = None,
    ) -> str:
        """Send an LLM chat request via the broker's queue."""
        params: dict[str, Any] = {"prompt": prompt, "temperature": temperature}
        if model:
            params["model"] = model
        if command:
            params["command"] = command
        if system:
            params["system"] = system
        return await self._service_request("llm", "chat", params)

    # ── Structured responses ────────────────────────────────────────

    async def respond_text(
        self, original: Message, text: str, format: str = "plain",
    ) -> None:
        """Send a text response."""
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_TEXT, "content": {"text": text, "format": format}},
        )
        await self._send(reply)

    async def respond_table(
        self,
        original: Message,
        columns: list[str],
        rows: list[list],
        title: str = "",
    ) -> None:
        """Send a table response."""
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_TABLE, "content": {"columns": columns, "rows": rows, "title": title}},
        )
        await self._send(reply)

    async def respond_list(
        self, original: Message, items: list[str], title: str = "",
    ) -> None:
        """Send a list response."""
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_LIST, "content": {"items": items, "title": title}},
        )
        await self._send(reply)

    async def respond_editor(
        self,
        original: Message,
        content: str,
        title: str = "",
        path: str = "",
        read_only: bool = False,
    ) -> None:
        """Send an editor response."""
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_EDITOR, "content": {
                "content": content, "title": title,
                "path": path, "read_only": read_only,
            }},
        )
        await self._send(reply)

    async def respond_confirm(
        self,
        original: Message,
        prompt: str,
        options: list[str],
        context: str = "",
    ) -> None:
        """Send a confirm response."""
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_CONFIRM, "content": {
                "prompt": prompt, "options": options, "context": context,
            }},
        )
        await self._send(reply)

    async def respond_error(
        self, original: Message, message: str, code: str = "",
    ) -> None:
        """Send an error response."""
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_ERROR, "content": {"message": message, "code": code}},
        )
        await self._send(reply)

    async def respond_progress(
        self, original: Message, message: str, percent: float | None = None,
    ) -> None:
        """Send a progress response."""
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_PROGRESS, "content": {
                "message": message, "percent": percent,
            }},
        )
        await self._send(reply)

    # ── Inter-agent ─────────────────────────────────────────────────

    async def send_to_agent(self, target_id: str, payload: dict) -> Message:
        """Send a message to another agent and wait for a reply."""
        msg = Message.create(
            MSG_AGENT_MESSAGE,
            sender=self.agent_id,
            to=target_id,
            payload=payload,
        )
        return await self._request(msg)

    # ── Settings ────────────────────────────────────────────────────

    async def get_setting(self, key: str) -> Any:
        return await self._service_request("settings", "get", {"key": key})

    async def get_model(self, command: str | None = None) -> str:
        params: dict[str, Any] = {}
        if command:
            params["command"] = command
        return await self._service_request("settings", "get_model", params)
