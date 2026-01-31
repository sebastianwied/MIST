"""Handler for the 'summarize' command."""

from .ollama_client import call_ollama
from .prompts import SUMMARIZATION_PROMPT
from .storage import RAWLOG_PATH, TO_SYNTH_PATH, JOURNAL_PATH


def handle_summarize() -> None:
    """Summarise pending notes, append to journal, and clear the synthesis file."""
    to_summarize = TO_SYNTH_PATH.read_text(encoding="utf-8")

    # Also append the raw notes to the log for archival
    with open(RAWLOG_PATH, "a") as f:
        f.write("\n")
        f.write(to_summarize)

    prompt = SUMMARIZATION_PROMPT.format(notes=to_summarize)
    summary = call_ollama(prompt)

    with open(JOURNAL_PATH, "a") as f:
        f.write(summary)
        f.write("\n")

    # Clear the pending-synthesis file
    TO_SYNTH_PATH.write_text("")
