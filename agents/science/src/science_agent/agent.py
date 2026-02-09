"""ScienceAgent — article search and library management agent."""

from __future__ import annotations

from mist_client import AgentBase

from .commands import dispatch
from .manifest import MANIFEST


class ScienceAgent(AgentBase):
    """Science agent for searching and managing scientific articles."""

    def manifest(self) -> dict:
        return MANIFEST

    async def handle_command(self, msg) -> None:
        await dispatch(self.client, msg)
