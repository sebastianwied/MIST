"""Handlers for note, notes, and recall commands."""

from .ollama_client import call_ollama
from .prompts import RECALL_PROMPT
from .storage import RawLogEntry, parse_all_entries, parse_rawlog, save_raw_input
from .types import Writer


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


def handle_recall(query: str) -> str:
    """Search all past entries (archive + rawLog + noteLogs) via LLM."""
    entries = parse_all_entries()
    if not entries:
        return "No entries to search."
    formatted = _format_entries(entries)
    prompt = RECALL_PROMPT.format(entries=formatted, query=query)
    return call_ollama(prompt, command="recall")
