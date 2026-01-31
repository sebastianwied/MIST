"""Command parsing and dispatch."""

from .respond import handle_text
from .summarize import handle_summarize
from .util import handle_status, stop_model

# Commands that are recognised as single bare words (no arguments).
_BARE_COMMANDS = {"status", "summarize", "stop", "debug"}


def dispatch(line: str, source: str = "terminal") -> str | None:
    """Route raw input to the appropriate handler.

    Single bare-word commands are matched exactly; everything else
    is passed through as free text, preserving quotes and punctuation.
    Returns the response string for free-text input, None for commands.
    """
    word = line.strip()

    if word == "status":
        handle_status()
    elif word == "summarize":
        handle_summarize()
    elif word == "stop":
        stop_model()
    elif word == "debug":
        pass
    else:
        return handle_text(line, source=source)
    return None
