"""Entry point for the MIST core process."""

from __future__ import annotations

import argparse
import asyncio
import logging

from .admin.agent import AdminAgent
from .db import Database
from .paths import Paths
from .broker.registry import AgentRegistry
from .broker.router import MessageRouter
from .broker.services import ServiceDispatcher
from .llm.client import OllamaClient
from .llm.queue import LLMQueue
from .storage.settings import Settings
from .transport import Server, WebSocketServer

log = logging.getLogger(__name__)


class Core:
    """Top-level orchestrator that owns all subsystems."""

    def __init__(
        self,
        paths: Paths | None = None,
        ws_host: str = "127.0.0.1",
        ws_port: int = 8765,
    ) -> None:
        self.paths = paths or Paths()
        self.db = Database(self.paths.db)
        self.settings = Settings(self.paths)
        self.llm_client = OllamaClient(self.settings)
        self.llm_queue = LLMQueue(self.llm_client)
        self.registry = AgentRegistry()
        self.services = ServiceDispatcher(self.paths, self.db, self.settings, self.llm_queue)
        self.router = MessageRouter(self.registry, self.services)
        self.admin = AdminAgent(
            paths=self.paths,
            db=self.db,
            settings=self.settings,
            llm_queue=self.llm_queue,
            registry=self.registry,
            services=self.services,
            router=self.router,
        )
        self._unix_server = Server(self.router.handle, path=self.paths.socket_path)
        self._ws_server = WebSocketServer(
            self.router.handle, host=ws_host, port=ws_port,
        )

    async def run(self) -> None:
        """Initialize and start all subsystems."""
        self.db.connect()
        self.db.init_schema()
        log.info("database initialized at %s", self.paths.db)

        self.admin.register()

        await self._unix_server.start()
        await self._ws_server.start()

        queue_task = asyncio.create_task(self.llm_queue.run())
        log.info("core started")

        try:
            await asyncio.gather(
                self._unix_server.serve_forever(),
                self._ws_server.serve_forever(),
            )
        except asyncio.CancelledError:
            log.info("core shutting down")
        finally:
            queue_task.cancel()
            try:
                await queue_task
            except asyncio.CancelledError:
                pass
            await self.shutdown()

    async def shutdown(self) -> None:
        await self._unix_server.stop()
        await self._ws_server.stop()
        self.llm_queue.stop()
        self.db.close()
        log.info("core stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="MIST core process")
    parser.add_argument(
        "--data-dir", default="data",
        help="Data directory (default: data)",
    )
    parser.add_argument(
        "--ws-host", default="127.0.0.1",
        help="WebSocket host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--ws-port", type=int, default=8765,
        help="WebSocket port (default: 8765)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    paths = Paths(root=args.data_dir)
    core = Core(paths=paths, ws_host=args.ws_host, ws_port=args.ws_port)
    asyncio.run(core.run())


if __name__ == "__main__":
    main()
