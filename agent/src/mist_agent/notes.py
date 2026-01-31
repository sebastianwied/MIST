"""Handlers for note, notes, and recall commands."""

from .ollama_client import call_ollama
from .prompts import RECALL_PROMPT
from .storage import RawLogEntry, parse_rawlog, save_raw_input


def _format_entries(entries: list[RawLogEntry]) -> str:
    """Format log entries as '[timestamp] (source) text' lines."""
    return "\n".join(
        f"[{e.time}] ({e.source}) {e.text}" for e in entries
    )


def handle_note(text: str) -> None:
    """Save a note silently (no LLM call)."""
    save_raw_input(text, source="note")
    print("Noted.")


def handle_notes(count: int = 10) -> None:
    """Print the last N notes."""
    entries = [e for e in parse_rawlog() if e.source == "note"]
    if not entries:
        print("No notes yet.")
        return
    for e in entries[-count:]:
        print(f"  [{e.time}] {e.text}")


def handle_recall(query: str) -> str:
    """Search all past entries via LLM and return the response."""
    entries = parse_rawlog()
    if not entries:
        return "No entries to search."
    formatted = _format_entries(entries)
    prompt = RECALL_PROMPT.format(entries=formatted, query=query)
    return call_ollama(prompt)
