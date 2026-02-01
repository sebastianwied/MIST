"""Handler for the 'summarize' command."""

from datetime import datetime

from .notes import _format_entries
from .ollama_client import call_ollama
from .prompts import SUMMARIZATION_PROMPT
from .storage import (
    JOURNAL_PATH,
    get_last_summarized_time,
    parse_rawlog,
    set_last_summarized_time,
)
from .types import Writer


def handle_summarize(output: Writer = print) -> None:
    """Summarise new rawLog entries since the last summarize, append to journal."""
    entries = parse_rawlog()
    high_water = get_last_summarized_time()

    if high_water:
        entries = [e for e in entries if e.time > high_water]

    if not entries:
        output("No new entries to summarize.")
        return

    output(f"Summarizing {len(entries)} entries...")
    formatted = _format_entries(entries)
    prompt = SUMMARIZATION_PROMPT.format(notes=formatted)
    summary = call_ollama(prompt)

    timestamp = datetime.now().isoformat(timespec="seconds")
    header = f"\n## Summary — {timestamp}\n\n"

    with open(JOURNAL_PATH, "a") as f:
        f.write(header)
        f.write(summary)
        f.write("\n")

    set_last_summarized_time(entries[-1].time)
    output("Summary appended to data/agentJournal.md.")
