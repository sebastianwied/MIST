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
