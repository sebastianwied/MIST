"""Handlers for note, notes, and recall commands."""

from __future__ import annotations

from typing import Any

from mist_client import BrokerClient
from mist_client.protocol import Message

from .prompts import RECALL_PROMPT


def _format_entries(entries: list[dict]) -> str:
    """Format log entries as '[timestamp] (source) text' lines."""
    return "\n".join(
        f"[{e.get('time', '')}] ({e.get('source', '')}) {e.get('text', '')}"
        for e in entries
    )


async def handle_note(client: BrokerClient, msg: Message, text: str) -> None:
    """Save a note (no LLM call)."""
    await client.save_raw_input(text, source="note")
    await client.respond_text(msg, "Noted.")


async def handle_notes(client: BrokerClient, msg: Message, count: int = 10) -> None:
    """Show the last N notes from the buffer."""
    entries = await client.parse_buffer()
    note_entries = [e for e in entries if e.get("source") == "note"]
    if not note_entries:
        await client.respond_text(msg, "No notes yet.")
        return

    lines = []
    for e in note_entries[-count:]:
        lines.append(f"[{e.get('time', '')}] {e.get('text', '')}")
    await client.respond_text(msg, "\n".join(lines))


async def handle_recall(client: BrokerClient, msg: Message, query: str) -> None:
    """Search all past entries via LLM."""
    entries = await client.parse_buffer()
    if not entries:
        await client.respond_text(msg, "No entries to search.")
        return

    formatted = _format_entries(entries)
    prompt = RECALL_PROMPT.format(entries=formatted, query=query)
    result = await client.llm_chat(prompt, command="recall")
    await client.respond_text(msg, result, format="markdown")


async def handle_topics(client: BrokerClient, msg: Message) -> None:
    """List all topics."""
    topics = await client.load_topic_index()
    if not topics:
        await client.respond_text(msg, "No topics yet. Run 'aggregate' first.")
        return

    items = [f"[{t.get('id', '')}] {t.get('slug', '')}: {t.get('name', '')}" for t in topics]
    await client.respond_list(msg, items, title="Topics")


async def handle_drafts(client: BrokerClient, msg: Message) -> None:
    """List draft notes."""
    drafts = await client.list_drafts()
    if not drafts:
        await client.respond_text(msg, "No draft notes.")
        return
    await client.respond_list(msg, drafts, title="Drafts")


async def handle_topic_view(client: BrokerClient, msg: Message, slug: str) -> None:
    """Return a topic's synthesis and list of notes for the browser panel."""
    if not slug:
        await client.respond_error(msg, "Usage: topic view <slug>")
        return

    topic = await client.find_topic(slug)
    if not topic:
        await client.respond_error(msg, f"Topic '{slug}' not found.")
        return

    actual_slug = topic.get("slug", slug)
    name = topic.get("name", actual_slug)
    synthesis = await client.load_topic_synthesis(actual_slug)
    notes = await client.list_topic_notes(actual_slug)
    buffer = await client.load_topic_buffer(actual_slug)

    # Return structured data the UI can render
    await client._send_response(msg, "topic_detail", {
        "slug": actual_slug,
        "name": name,
        "synthesis": synthesis,
        "notes": notes,
        "buffer_count": len(buffer),
    })


async def handle_topic_read(
    client: BrokerClient, msg: Message, slug: str, filename: str,
) -> None:
    """Read a file from a topic and return it as an editor response."""
    if not slug:
        await client.respond_error(msg, "Usage: topic read <slug> [filename]")
        return

    topic = await client.find_topic(slug)
    if not topic:
        await client.respond_error(msg, f"Topic '{slug}' not found.")
        return

    actual_slug = topic.get("slug", slug)
    name = topic.get("name", actual_slug)

    if filename == "synthesis":
        content = await client.load_topic_synthesis(actual_slug)
        title = f"{name} — Synthesis"
    else:
        content = await client.load_topic_note(actual_slug, filename)
        title = f"{name} — {filename}"

    await client.respond_editor(
        msg, content or "", title=title,
        path=f"{actual_slug}/{filename}", read_only=False,
    )


async def handle_topic_write(
    client: BrokerClient, msg: Message,
    slug: str, filename: str, content: str,
) -> None:
    """Save content to a topic file."""
    if not slug or not content:
        await client.respond_error(msg, "Missing slug or content.")
        return

    topic = await client.find_topic(slug)
    if not topic:
        await client.respond_error(msg, f"Topic '{slug}' not found.")
        return

    actual_slug = topic.get("slug", slug)

    if filename == "synthesis":
        await client.save_topic_synthesis(actual_slug, content)
    else:
        await client.save_topic_note(actual_slug, filename, content)

    await client.respond_text(msg, f"Saved {filename} in {actual_slug}.")
