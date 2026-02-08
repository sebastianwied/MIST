"""Handlers for note, notes, and recall commands."""

import json

from mist_core.ollama_client import call_ollama
from mist_core.storage import (
    RawLogEntry, create_draft_note, create_topic_note,
    file_draft_to_topic, find_topic,
    list_draft_notes, list_topic_notes,
    load_draft_note, load_topic_note, load_topic_notelog,
    load_topic_synthesis, save_topic_note,
    parse_all_entries, parse_rawlog, save_raw_input,
)
from mist_core.types import Writer

from .prompts import (
    NOTE_PROMOTE_DEEP_PROMPT,
    NOTE_PROMOTE_DRAFT_PROMPT,
    NOTE_PROMOTE_OUTLINE_PROMPT,
    RECALL_PROMPT,
)


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


def handle_note_edit(topic_id: str, filename: str, output: Writer = print) -> None:
    """Open an existing note file for editing."""
    if not topic_id or not filename:
        output("Usage: note edit <topic|drafts> <filename>")
        return
    if topic_id.lower() == "drafts":
        content = load_draft_note(filename)
        slug = "__draft__"
    else:
        topic = find_topic(topic_id)
        if topic is None:
            output(f"Topic '{topic_id}' not found.")
            return
        slug = topic.slug
        content = load_topic_note(slug, filename)
    if not content:
        output(f"Note '{filename}' not found.")
        return
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


def handle_note_file(filename: str, topic_id: str, output: Writer = print) -> None:
    """Move a draft note into a topic's notes/ directory."""
    if not filename or not topic_id:
        output("Usage: note file <filename> <topic>")
        return
    content = load_draft_note(filename)
    if not content:
        output(f"Draft '{filename}' not found.")
        return
    topic = find_topic(topic_id)
    if topic is None:
        output(f"Topic '{topic_id}' not found.")
        return
    final = file_draft_to_topic(filename, topic.slug)
    output(f"Filed '{final}' to topic '{topic.name}'.")


def handle_note_promote(
    topic_id: str, entry_index: str, depth: str, output: Writer = print,
) -> None:
    """Expand a noteLog entry into a standalone .md note via LLM."""
    topic = find_topic(topic_id)
    if topic is None:
        output(f"Topic '{topic_id}' not found.")
        return

    entries = load_topic_notelog(topic.slug)
    try:
        idx = int(entry_index)
    except ValueError:
        output(f"Invalid entry index: '{entry_index}'")
        return
    if idx < 0 or idx >= len(entries):
        output(f"Entry index {idx} out of range (0-{len(entries) - 1}).")
        return

    entry = entries[idx]
    synthesis = load_topic_synthesis(topic.slug) or "(no synthesis yet)"

    prompts = {
        "outline": NOTE_PROMOTE_OUTLINE_PROMPT,
        "draft": NOTE_PROMOTE_DRAFT_PROMPT,
        "deep": NOTE_PROMOTE_DEEP_PROMPT,
    }
    template = prompts.get(depth, NOTE_PROMOTE_DRAFT_PROMPT)
    prompt = template.format(
        entry_text=entry.text,
        topic_name=topic.name,
        topic_synthesis=synthesis,
    )
    result = call_ollama(prompt, command="promote")

    # Derive a short title from the entry text
    title = entry.text[:50].strip().rstrip(".")
    filename, path = create_topic_note(topic.slug, title)
    save_topic_note(topic.slug, filename, result)
    output(json.dumps({"slug": topic.slug, "filename": filename, "content": result}))


def handle_recall(query: str) -> str:
    """Search all past entries (archive + rawLog + noteLogs) via LLM."""
    entries = parse_all_entries()
    if not entries:
        return "No entries to search."
    formatted = _format_entries(entries)
    prompt = RECALL_PROMPT.format(entries=formatted, query=query)
    return call_ollama(prompt, command="recall")
