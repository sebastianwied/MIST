"""LLM-based extraction of tasks and events from free text."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from ..llm.queue import LLMQueue, PRIORITY_ADMIN
from ..storage.events import EventStore
from ..storage.tasks import TaskStore
from .prompts import EXTRACTION_PROMPT

log = logging.getLogger(__name__)


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


async def extract_items(
    text: str,
    llm_queue: LLMQueue,
) -> dict[str, list[dict[str, Any]]]:
    """Ask the LLM to extract tasks and events from *text*.

    Returns {"tasks": [...], "events": [...]}.
    On parse failure returns empty lists.
    """
    prompt = EXTRACTION_PROMPT.format(text=text)
    try:
        raw = await llm_queue.submit(
            prompt=prompt,
            priority=PRIORITY_ADMIN,
            temperature=0.1,
            command="extract",
        )
    except Exception:
        log.exception("LLM extraction failed")
        return {"tasks": [], "events": []}

    cleaned = _strip_code_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        log.warning("extraction returned invalid JSON: %s", cleaned[:200])
        return {"tasks": [], "events": []}

    if not isinstance(data, dict):
        return {"tasks": [], "events": []}

    tasks = data.get("tasks", [])
    events = data.get("events", [])
    if not isinstance(tasks, list):
        tasks = []
    if not isinstance(events, list):
        events = []
    return {"tasks": tasks, "events": events}


async def apply_extracted_items(
    items: dict[str, list[dict[str, Any]]],
    tasks_store: TaskStore,
    events_store: EventStore,
) -> list[str]:
    """Create extracted tasks/events in the database.

    Returns a list of summary strings describing what was created.
    """
    created: list[str] = []

    for t in items.get("tasks", []):
        title = t.get("title", "").strip()
        if not title:
            continue
        due = t.get("due_date")
        task_id = await asyncio.to_thread(tasks_store.create, title=title, due_date=due)
        desc = f"Created task #{task_id}: {title}"
        if due:
            desc += f" (due {due})"
        created.append(desc)

    for e in items.get("events", []):
        title = e.get("title", "").strip()
        start = e.get("start_time")
        if not title or not start:
            continue
        end = e.get("end_time")
        freq = e.get("frequency")
        event_id = await asyncio.to_thread(
            events_store.create,
            title=title,
            start_time=start,
            end_time=end,
            frequency=freq,
        )
        desc = f"Created event #{event_id}: {title} at {start}"
        if freq:
            desc += f" ({freq})"
        created.append(desc)

    return created
