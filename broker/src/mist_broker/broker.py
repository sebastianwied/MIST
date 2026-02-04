"""Broker orchestrator: wires Server + subsystems."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from mist_core.protocol import Message
from mist_core.transport import Connection, Server, DEFAULT_SOCKET_PATH

from .registry import AgentRegistry
from .router import MessageRouter
from .services import ServiceDispatcher
from .llm_service import LLMService

log = logging.getLogger(__name__)


class Broker:
    """Top-level broker that owns the Server and all subsystems."""

    def __init__(self, socket_path: Path | str = DEFAULT_SOCKET_PATH) -> None:
        self._registry = AgentRegistry()
        self._services = ServiceDispatcher()
        self._llm = LLMService()
        self._router = MessageRouter(self._registry, self._services, self._llm)
        self._server = Server(self._handle_message, path=socket_path)

    async def run(self) -> None:
        """Initialize services, start listening, and serve until cancelled."""
        self._services.initialize()
        await self._server.start()
        log.info("broker started")
        try:
            await self._server.serve_forever()
        except asyncio.CancelledError:
            log.info("broker shutting down")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Stop the server and clean up."""
        await self._server.stop()
        log.info("broker stopped")

    async def _handle_message(self, msg: Message, conn: Connection) -> None:
        await self._router.handle(msg, conn)
