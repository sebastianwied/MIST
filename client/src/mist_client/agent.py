"""AgentBase — connect/register/message-loop boilerplate for agents."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from .client import BrokerClient
from .protocol import (
    Message,
    MSG_AGENT_REGISTER,
    MSG_AGENT_READY,
    MSG_AGENT_DISCONNECT,
    MSG_COMMAND,
    MSG_AGENT_MESSAGE,
    encode_message,
    decode_message,
)

log = logging.getLogger(__name__)

DEFAULT_SOCKET_PATH = Path("data/broker/mist.sock")


class AgentBase:
    """Base class for MIST agents.

    Subclass and override ``manifest()`` and ``handle_command()``.

    Usage:
        class MyAgent(AgentBase):
            def manifest(self) -> dict:
                return {"name": "my-agent", "commands": [...]}

            async def handle_command(self, msg: Message) -> None:
                await self.client.respond_text(msg, "Hello!")

        agent = MyAgent()
        asyncio.run(agent.run())
    """

    def __init__(self, socket_path: Path | str = DEFAULT_SOCKET_PATH) -> None:
        self._socket_path = Path(socket_path)
        self.client: BrokerClient | None = None
        self.agent_id: str | None = None

    def manifest(self) -> dict[str, Any]:
        """Return the agent's manifest. Override in subclass."""
        raise NotImplementedError("subclass must override manifest()")

    async def handle_command(self, msg: Message) -> None:
        """Handle an incoming command. Override in subclass."""
        raise NotImplementedError("subclass must override handle_command()")

    async def on_agent_message(self, msg: Message) -> None:
        """Handle an inter-agent message. Override if needed."""
        log.warning("unhandled agent message from %s", msg.sender)

    async def run(self) -> None:
        """Connect, register, and loop handling commands."""
        # Connect to broker
        reader, writer = await asyncio.open_unix_connection(
            str(self._socket_path)
        )

        try:
            # Send registration
            manifest = self.manifest()
            reg_msg = Message.create(
                MSG_AGENT_REGISTER,
                sender="pending",
                to="broker",
                payload=manifest,
            )
            writer.write((encode_message(reg_msg) + "\n").encode())
            await writer.drain()

            # Wait for ready
            raw = await reader.readuntil(b"\n")
            ready = decode_message(raw.decode().rstrip("\n"))
            if ready.type != MSG_AGENT_READY:
                raise RuntimeError(f"expected agent.ready, got {ready.type}")
            self.agent_id = ready.payload["agent_id"]
            log.info("registered as %s", self.agent_id)

            # Create BrokerClient now that we have agent_id
            self.client = BrokerClient(self.agent_id, self._socket_path)
            # Inject the existing connection into the client
            self.client._reader = reader
            self.client._writer = writer
            self.client._listen_task = asyncio.create_task(self.client._listen_loop())

            # Command loop
            while True:
                msg = await self.client.recv_command()
                try:
                    if msg.type == MSG_AGENT_MESSAGE:
                        await self.on_agent_message(msg)
                    else:
                        await self.handle_command(msg)
                except Exception:
                    log.exception("error handling %s", msg.type)
                    if msg.type == MSG_COMMAND:
                        await self.client.respond_error(msg, "internal agent error")

        except asyncio.CancelledError:
            log.info("agent shutting down")
        finally:
            # Send disconnect
            if self.agent_id:
                try:
                    disc = Message.create(
                        MSG_AGENT_DISCONNECT,
                        sender=self.agent_id,
                        to="broker",
                    )
                    writer.write((encode_message(disc) + "\n").encode())
                    await writer.drain()
                except Exception:
                    pass
            if self.client and self.client._listen_task:
                self.client._listen_task.cancel()
                try:
                    await self.client._listen_task
                except asyncio.CancelledError:
                    pass
            writer.close()
            await writer.wait_closed()
