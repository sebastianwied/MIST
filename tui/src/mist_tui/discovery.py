"""Discover installed MIST agents via entry points."""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "mist.agents"


def discover_agents() -> list[dict]:
    """Scan installed packages for mist.agents entry points.

    Each entry point should resolve to a dict with keys:
        name, command, description
    """
    agents: list[dict] = []
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except Exception:
        log.warning("failed to query entry points for %s", ENTRY_POINT_GROUP)
        return agents

    for ep in eps:
        try:
            entry = ep.load()
            if isinstance(entry, dict) and "command" in entry:
                agents.append(entry)
            else:
                log.warning("entry point %s did not resolve to a valid dict", ep.name)
        except Exception:
            log.warning("failed to load entry point %s", ep.name, exc_info=True)

    return agents
