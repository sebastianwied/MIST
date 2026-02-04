"""Handlers for note, notes, and recall commands."""

import json

from mist_core.ollama_client import call_ollama
from mist_core.storage import (
    RawLogEntry, create_draft_note, create_topic_note, find_topic,
    list_draft_notes, list_topic_notes,
    parse_all_entries, parse_rawlog, save_raw_input,
)
from mist_core.types import Writer

from .prompts import RECALL_PROMPT


def _format_entries(entries: list[RawLogEntry]) -> str:
    """Format log entries as '[timestamp] (source) text' lines."""
    return "\n".join(
        f"[{e.time}] ({e.source}) {e.text}" for e in entries
    )


def handle_note(text: str, output: Writer = print) -> None:
    """Save a note silently (no LLM call)."""
    save_raw_input(text, source="note")
    output("Noted.")


def handle_notes(count: int = 10, output: Writer = print) -> None:
    """Print the last N notes."""
    entries = [e for e in parse_rawlog() if e.source == "note"]
    if not entries:
        output("No notes yet.")
        return
    for e in entries[-count:]:
        output(f"  [{e.time}] {e.text}")


def handle_note_new(topic_id: str, title: str, output: Writer = print) -> None:
    """Create a new note file in a topic folder, or as a draft if no topic matches."""
    if not topic_id:
        output("Usage: note new [topic] <title>")
        return
    topic = find_topic(topic_id)
    if topic is not None:
        if not title:
            output("Usage: note new <topic> <title>")
            return
        filename, path = create_topic_note(topic.slug, title)
        slug = topic.slug
    else:
        # First word wasn't a topic — treat entire input as title
        full_title = f"{topic_id} {title}".strip() if title else topic_id
        filename, path = create_draft_note(full_title)
        slug = "__draft__"
    content = path.read_text(encoding="utf-8")
    output(json.dumps({"slug": slug, "filename": filename, "content": content}))


def handle_note_list(topic_id: str, output: Writer = print) -> None:
    """List notes in a topic folder or drafts."""
    if topic_id.lower() == "drafts":
        notes = list_draft_notes()
        if not notes:
            output("No draft notes.")
            return
        output("Draft notes:")
        for n in notes:
            output(f"  {n}")
        return
    topic = find_topic(topic_id)
    if topic is None:
        output(f"Topic '{topic_id}' not found.")
        return
    notes = list_topic_notes(topic.slug)
    if not notes:
        output(f"No notes in topic '{topic.name}'.")
        return
    output(f"Notes in {topic.name}:")
    for n in notes:
        output(f"  {n}")


def handle_recall(query: str) -> str:
    """Search all past entries (archive + rawLog + noteLogs) via LLM."""
    entries = parse_all_entries()
    if not entries:
        return "No entries to search."
    formatted = _format_entries(entries)
    prompt = RECALL_PROMPT.format(entries=formatted, query=query)
    return call_ollama(prompt, command="recall")
