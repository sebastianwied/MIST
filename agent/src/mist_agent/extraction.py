"""LLM-based extraction of tasks and events from free text."""

import json
import re
from typing import Any, Callable

from .event_store import create_event
from .ollama_client import call_ollama
from .prompts import EXTRACTION_PROMPT
from .task_store import create_task
from .types import Writer


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def extract_items(text: str) -> dict[str, list[dict[str, Any]]]:
    """Ask the LLM to extract tasks and events from *text*.

    Returns {"tasks": [...], "events": [...]}.
    On parse failure returns empty lists.
    """
    prompt = EXTRACTION_PROMPT.format(text=text)
    raw = call_ollama(prompt, temperature=0.1)
    cleaned = _strip_code_fences(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
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


def apply_extracted_items(
    items: dict[str, list[dict[str, Any]]],
    output: Writer = print,
    confirm_fn: Callable[[str], bool] | None = None,
) -> None:
    """Create extracted tasks/events in the database.

    If *confirm_fn* is provided, each item is confirmed before creation.
    If *confirm_fn* is None, items are created directly (auto mode).
    """
    tasks = items.get("tasks", [])
    events = items.get("events", [])

    for t in tasks:
        title = t.get("title", "").strip()
        if not title:
            continue
        due = t.get("due_date")
        desc = f"Task: {title}"
        if due:
            desc += f" (due {due})"

        if confirm_fn and not confirm_fn(f"Create task: {title}" + (f" due:{due}" if due else "") + "?"):
            output(f"  Skipped task: {title}")
            continue

        task_id = create_task(title, due_date=due)
        output(f"  Created task #{task_id}: {title}" + (f" (due {due})" if due else ""))

    for e in events:
        title = e.get("title", "").strip()
        start = e.get("start_time")
        if not title or not start:
            continue
        end = e.get("end_time")
        freq = e.get("frequency")
        desc = f"Event: {title} at {start}"
        if freq:
            desc += f" ({freq})"

        if confirm_fn and not confirm_fn(f"Create event: {title} at {start}" + (f" ({freq})" if freq else "") + "?"):
            output(f"  Skipped event: {title}")
            continue

        event_id = create_event(title, start_time=start, end_time=end, frequency=freq)
        output(f"  Created event #{event_id}: {title} at {start}" + (f" ({freq})" if freq else ""))
