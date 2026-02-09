"""Message router: dispatch by message type."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ..protocol import (
    Message,
    MSG_AGENT_CATALOG,
    MSG_AGENT_DISCONNECT,
    MSG_AGENT_LIST,
    MSG_AGENT_MESSAGE,
    MSG_AGENT_BROADCAST,
    MSG_AGENT_READY,
    MSG_AGENT_REGISTER,
    MSG_COMMAND,
    MSG_ERROR,
    MSG_RESPONSE,
    MSG_SERVICE_REQUEST,
)
from ..transport import Connection, WebSocketConnection

from .registry import AgentRegistry
from .services import ServiceDispatcher

log = logging.getLogger(__name__)

BROKER_ID = "broker"

# Type for the admin agent's in-process handler
AdminHandler = Callable[[Message], Awaitable[None]]


@dataclass
class PendingCommand:
    """Tracks an in-flight command for response routing."""

    msg_id: str
    origin_conn: Connection | WebSocketConnection
    target_agent_id: str


class MessageRouter:
    """Dispatch incoming messages to the appropriate subsystem."""

    def __init__(
        self,
        registry: AgentRegistry,
        services: ServiceDispatcher,
    ) -> None:
        self._registry = registry
        self._services = services
        self._pending: dict[str, PendingCommand] = {}
        self._admin_handler: AdminHandler | None = None
        self._ui_connections: list[WebSocketConnection] = []

    def set_admin_handler(self, handler: AdminHandler) -> None:
        """Set the in-process admin agent's message handler."""
        self._admin_handler = handler

    def add_ui_connection(self, conn: WebSocketConnection) -> None:
        self._ui_connections.append(conn)

    def remove_ui_connection(self, conn: WebSocketConnection) -> None:
        self._ui_connections = [c for c in self._ui_connections if c is not conn]

    async def broadcast_to_ui(self, msg: Message) -> None:
        """Send a message to all connected UI clients."""
        for conn in list(self._ui_connections):
            try:
                await conn.send(msg)
            except Exception:
                self.remove_ui_connection(conn)

    async def handle(self, msg: Message, conn: Connection | WebSocketConnection) -> None:
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
                case "service.request":
                    await self._on_service_request(msg, conn)
                case "agent.message":
                    await self._on_agent_message(msg, conn)
                case "agent.broadcast":
                    await self._on_agent_broadcast(msg, conn)
                case _:
                    await self._send_error(
                        msg, conn, f"unknown message type: {msg.type}",
                    )
        except (ConnectionResetError, BrokenPipeError) as exc:
            log.warning("connection lost during handling: %s", exc)
            if isinstance(conn, Connection):
                entry = self._registry.unregister_by_conn(conn)
                if entry:
                    log.info("removed disconnected agent: %s", entry.agent_id)
                    self._cleanup_pending_for(entry.agent_id)

    # ── Handlers ─────────────────────────────────────────────────────

    async def _on_register(self, msg: Message, conn: Connection | WebSocketConnection) -> None:
        manifest = msg.payload
        entry = self._registry.register(conn, manifest)
        log.info("registered agent: %s (name=%s)", entry.agent_id, entry.name)
        reply = Message.reply(
            msg, BROKER_ID, MSG_AGENT_READY, {"agent_id": entry.agent_id},
        )
        await conn.send(reply)

    async def _on_disconnect(self, msg: Message, conn: Connection | WebSocketConnection) -> None:
        if isinstance(conn, Connection):
            entry = self._registry.unregister_by_conn(conn)
            if entry:
                log.info("agent disconnected: %s", entry.agent_id)
                self._cleanup_pending_for(entry.agent_id)

    async def _on_list(self, msg: Message, conn: Connection | WebSocketConnection) -> None:
        catalog = self._registry.build_catalog()
        reply = Message.reply(
            msg, BROKER_ID, MSG_AGENT_CATALOG, {"agents": catalog},
        )
        await conn.send(reply)

    async def _on_command(self, msg: Message, conn: Connection | WebSocketConnection) -> None:
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

        # In-process admin agent
        if target.privileged and target.conn is None and self._admin_handler:
            await self._admin_handler(msg)
            return

        # External agent
        if target.conn is None:
            del self._pending[msg.id]
            await self._send_error(msg, conn, f"agent has no connection: {target_id}")
            return

        try:
            await target.conn.send(msg)
        except (ConnectionResetError, BrokenPipeError):
            log.warning("failed to forward command to %s", target_id)
            del self._pending[msg.id]
            self._registry.unregister(target_id)
            self._cleanup_pending_for(target_id)
            await self._send_error(msg, conn, f"agent disconnected: {target_id}")

    async def _on_response(self, msg: Message, conn: Connection | WebSocketConnection) -> None:
        pending = self._pending.pop(msg.reply_to, None) if msg.reply_to else None
        if pending is None:
            log.warning("response with no pending command: reply_to=%s", msg.reply_to)
            return
        try:
            await pending.origin_conn.send(msg)
        except (ConnectionResetError, BrokenPipeError):
            log.warning("failed to forward response to origin")

    async def _on_service_request(self, msg: Message, conn: Connection | WebSocketConnection) -> None:
        await self._services.handle(msg, conn)

    async def _on_agent_message(self, msg: Message, conn: Connection | WebSocketConnection) -> None:
        """Route a message from one agent to another."""
        target_id = msg.to
        target = self._registry.get_by_id(target_id)
        if target is None:
            await self._send_error(msg, conn, f"unknown agent: {target_id}")
            return

        if target.privileged and target.conn is None and self._admin_handler:
            await self._admin_handler(msg)
            return

        if target.conn is None:
            await self._send_error(msg, conn, f"agent has no connection: {target_id}")
            return

        try:
            await target.conn.send(msg)
        except (ConnectionResetError, BrokenPipeError):
            await self._send_error(msg, conn, f"agent disconnected: {target_id}")

    async def _on_agent_broadcast(self, msg: Message, conn: Connection | WebSocketConnection) -> None:
        """Forward a message to all connected agents except the sender."""
        sender_entry = None
        if isinstance(conn, Connection):
            sender_entry = self._registry.get_by_conn(conn)

        for entry in self._registry.all_agents():
            if sender_entry and entry.agent_id == sender_entry.agent_id:
                continue
            if entry.conn is None:
                if entry.privileged and self._admin_handler:
                    await self._admin_handler(msg)
                continue
            try:
                await entry.conn.send(msg)
            except (ConnectionResetError, BrokenPipeError):
                pass

    # ── Helpers ──────────────────────────────────────────────────────

    async def _send_error(
        self, msg: Message, conn: Connection | WebSocketConnection, error: str,
    ) -> None:
        reply = Message.reply(msg, BROKER_ID, MSG_ERROR, {"error": error})
        try:
            await conn.send(reply)
        except (ConnectionResetError, BrokenPipeError):
            log.warning("failed to send error to client")

    def _cleanup_pending_for(self, agent_id: str) -> None:
        to_remove = [
            mid for mid, pc in self._pending.items()
            if pc.target_agent_id == agent_id
        ]
        for mid in to_remove:
            del self._pending[mid]
