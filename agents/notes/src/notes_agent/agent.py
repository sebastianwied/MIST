"""NotesAgent — note-taking and knowledge synthesis agent."""

from __future__ import annotations

import asyncio
import logging

from mist_client import AgentBase

from .commands import dispatch
from .manifest import MANIFEST


class NotesAgent(AgentBase):
    """Notes agent that handles note-taking, topics, aggregation, and synthesis."""

    def manifest(self) -> dict:
        return MANIFEST

    async def handle_command(self, msg) -> None:
        await dispatch(self.client, msg)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    agent = NotesAgent()
    asyncio.run(agent.run())
