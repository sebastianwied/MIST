"""Message router: dispatch by message type."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from mist_core.protocol import (
    Message,
    MSG_AGENT_CATALOG,
    MSG_AGENT_DISCONNECT,
    MSG_AGENT_LIST,
    MSG_AGENT_READY,
    MSG_AGENT_REGISTER,
    MSG_COMMAND,
    MSG_ERROR,
    MSG_RESPONSE,
    MSG_RESPONSE_CHUNK,
    MSG_RESPONSE_END,
    MSG_SERVICE_REQUEST,
)
from mist_core.transport import Connection

from .registry import AgentRegistry
from .services import ServiceDispatcher
from .llm_service import LLMService

log = logging.getLogger(__name__)

BROKER_ID = "broker"


@dataclass
class PendingCommand:
    """Tracks an in-flight command for response routing."""

    msg_id: str
    origin_conn: Connection
    target_agent_id: str


class MessageRouter:
    """Dispatch incoming messages to the appropriate subsystem."""

    def __init__(
        self,
        registry: AgentRegistry,
        services: ServiceDispatcher,
        llm: LLMService,
    ) -> None:
        self._registry = registry
        self._services = services
        self._llm = llm
        self._pending: dict[str, PendingCommand] = {}

    async def handle(self, msg: Message, conn: Connection) -> None:
        """Main dispatch — route by msg.type."""
        try:
            match msg.type:
                case "agent.register":
                    await self._on_register(msg, conn)
                case "agent.disconnect":
                    await self._on_disconnect(msg, conn)
                case "agent.list":
                    await self._on_list(msg, conn)
                case "command":
                    await self._on_command(msg, conn)
                case "response":
                    await self._on_response(msg, conn)
                case "response.chunk":
                    await self._on_response_chunk(msg, conn)
                case "response.end":
                    await self._on_response_end(msg, conn)
                case "service.request":
                    await self._on_service_request(msg, conn)
                case _:
                    await self._send_error(
                        msg, conn, f"unknown message type: {msg.type}",
                    )
        except (ConnectionResetError, BrokenPipeError) as exc:
            log.warning("connection lost during handling: %s", exc)
            entry = self._registry.unregister_by_conn(conn)
            if entry:
                log.info("removed disconnected agent: %s", entry.agent_id)
                self._cleanup_pending_for(entry.agent_id)

    # ── Handlers ─────────────────────────────────────────────────────

    async def _on_register(self, msg: Message, conn: Connection) -> None:
        manifest = msg.payload
        entry = self._registry.register(conn, manifest)
        log.info("registered agent: %s (name=%s)", entry.agent_id, entry.name)
        reply = Message.reply(
            msg,
            BROKER_ID,
            MSG_AGENT_READY,
            {"agent_id": entry.agent_id},
        )
        await conn.send(reply)

    async def _on_disconnect(self, msg: Message, conn: Connection) -> None:
        entry = self._registry.unregister_by_conn(conn)
        if entry:
            log.info("agent disconnected: %s", entry.agent_id)
            self._cleanup_pending_for(entry.agent_id)

    async def _on_list(self, msg: Message, conn: Connection) -> None:
        catalog = self._registry.build_catalog()
        reply = Message.reply(
            msg, BROKER_ID, MSG_AGENT_CATALOG, {"agents": catalog},
        )
        await conn.send(reply)

    async def _on_command(self, msg: Message, conn: Connection) -> None:
        target_id = msg.to
        target = self._registry.get_by_id(target_id)
        if target is None:
            await self._send_error(msg, conn, f"unknown agent: {target_id}")
            return

        # Track the pending command for response routing
        self._pending[msg.id] = PendingCommand(
            msg_id=msg.id,
            origin_conn=conn,
            target_agent_id=target_id,
        )
        try:
            await target.conn.send(msg)
        except (ConnectionResetError, BrokenPipeError):
            log.warning("failed to forward command to %s", target_id)
            del self._pending[msg.id]
            self._registry.unregister(target_id)
            self._cleanup_pending_for(target_id)
            await self._send_error(msg, conn, f"agent disconnected: {target_id}")

    async def _on_response(self, msg: Message, conn: Connection) -> None:
        pending = self._pending.pop(msg.reply_to, None) if msg.reply_to else None
        if pending is None:
            log.warning("response with no pending command: reply_to=%s", msg.reply_to)
            return
        try:
            await pending.origin_conn.send(msg)
        except (ConnectionResetError, BrokenPipeError):
            log.warning("failed to forward response to origin")

    async def _on_response_chunk(self, msg: Message, conn: Connection) -> None:
        pending = self._pending.get(msg.reply_to) if msg.reply_to else None
        if pending is None:
            log.warning("response.chunk with no pending command: reply_to=%s", msg.reply_to)
            return
        try:
            await pending.origin_conn.send(msg)
        except (ConnectionResetError, BrokenPipeError):
            log.warning("failed to forward chunk to origin")

    async def _on_response_end(self, msg: Message, conn: Connection) -> None:
        pending = self._pending.pop(msg.reply_to, None) if msg.reply_to else None
        if pending is None:
            log.warning("response.end with no pending command: reply_to=%s", msg.reply_to)
            return
        try:
            await pending.origin_conn.send(msg)
        except (ConnectionResetError, BrokenPipeError):
            log.warning("failed to forward response.end to origin")

    async def _on_service_request(self, msg: Message, conn: Connection) -> None:
        service = msg.payload.get("service")
        if service == "llm":
            await self._llm.handle(msg, conn)
        else:
            await self._services.handle(msg, conn)

    # ── Helpers ──────────────────────────────────────────────────────

    async def _send_error(
        self, msg: Message, conn: Connection, error: str,
    ) -> None:
        reply = Message.reply(msg, BROKER_ID, MSG_ERROR, {"error": error})
        try:
            await conn.send(reply)
        except (ConnectionResetError, BrokenPipeError):
            log.warning("failed to send error to client")

    def _cleanup_pending_for(self, agent_id: str) -> None:
        """Remove all pending commands targeting a disconnected agent."""
        to_remove = [
            mid for mid, pc in self._pending.items()
            if pc.target_agent_id == agent_id
        ]
        for mid in to_remove:
            del self._pending[mid]
