"""ScienceAgent — article search and library management agent."""

from __future__ import annotations

import asyncio
import logging

from mist_client import AgentBase

from .commands import dispatch
from .manifest import MANIFEST


class ScienceAgent(AgentBase):
    """Science agent for searching and managing scientific articles."""

    def manifest(self) -> dict:
        return MANIFEST

    async def handle_command(self, msg) -> None:
        await dispatch(self.client, msg)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    agent = ScienceAgent()
    asyncio.run(agent.run())
