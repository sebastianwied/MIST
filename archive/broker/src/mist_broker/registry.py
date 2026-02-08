"""Agent registry: connection tracking and lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mist_core.transport import Connection


@dataclass
class AgentEntry:
    """A connected agent tracked by the broker."""

    agent_id: str
    name: str
    manifest: dict[str, Any]
    conn: Connection


class AgentRegistry:
    """Tracks connected agents and maps connections to agent IDs."""

    def __init__(self) -> None:
        self._agents: dict[str, AgentEntry] = {}
        self._conn_to_agent: dict[int, str] = {}
        self._name_counter: dict[str, int] = {}

    def register(self, conn: Connection, manifest: dict[str, Any]) -> AgentEntry:
        """Assign a unique ID, store the agent, and return the entry."""
        name = manifest.get("name", "agent")
        suffix = self._name_counter.get(name, 0)
        self._name_counter[name] = suffix + 1
        agent_id = f"{name}-{suffix}"

        entry = AgentEntry(
            agent_id=agent_id,
            name=name,
            manifest=manifest,
            conn=conn,
        )
        self._agents[agent_id] = entry
        self._conn_to_agent[id(conn)] = agent_id
        return entry

    def unregister(self, agent_id: str) -> AgentEntry | None:
        """Remove an agent by ID. Returns the entry or None."""
        entry = self._agents.pop(agent_id, None)
        if entry is not None:
            self._conn_to_agent.pop(id(entry.conn), None)
        return entry

    def unregister_by_conn(self, conn: Connection) -> AgentEntry | None:
        """Remove an agent by its connection. Returns the entry or None."""
        agent_id = self._conn_to_agent.pop(id(conn), None)
        if agent_id is not None:
            return self._agents.pop(agent_id, None)
        return None

    def get_by_id(self, agent_id: str) -> AgentEntry | None:
        """Look up an agent by ID."""
        return self._agents.get(agent_id)

    def get_by_conn(self, conn: Connection) -> AgentEntry | None:
        """Look up an agent by its connection."""
        agent_id = self._conn_to_agent.get(id(conn))
        if agent_id is not None:
            return self._agents.get(agent_id)
        return None

    def all_agents(self) -> list[AgentEntry]:
        """Return all connected agents."""
        return list(self._agents.values())

    def build_catalog(self) -> list[dict]:
        """Build a catalog of connected agents for agent.catalog responses."""
        return [
            {
                "agent_id": e.agent_id,
                "name": e.name,
                "commands": e.manifest.get("commands", []),
                "description": e.manifest.get("description", ""),
                "widgets": e.manifest.get("widgets", []),
            }
            for e in self._agents.values()
        ]
