"""Command parsing and dispatch."""

from .notes import handle_note, handle_notes, handle_recall
from .persona_command import handle_persona
from .respond import handle_text
from .summarize import handle_summarize
from .synthesis import handle_resynth, handle_sync
from .util import handle_status, stop_model


def dispatch(line: str, source: str = "terminal") -> str | None:
    """Route raw input to the appropriate handler.

    Prefix commands (note, recall) consume the rest of the line as an argument.
    Bare commands are matched as single words.
    Everything else is passed through as free text.
    Returns the response string for free-text / recall, None for other commands.
    """
    stripped = line.strip()
    cmd, _, arg = stripped.partition(" ")
    cmd = cmd.lower()
    arg = arg.strip()

    # --- prefix commands (require an argument) ---
    if cmd == "note" and arg:
        handle_note(arg)
        return None
    if cmd == "recall" and arg:
        return handle_recall(arg)

    # --- bare commands ---
    if stripped == "notes":
        handle_notes()
        return None
    if stripped == "sync":
        handle_sync()
        return None
    if stripped == "resynth":
        handle_resynth()
        return None
    if stripped == "summarize":
        handle_summarize()
        return None
    if stripped == "status":
        handle_status()
        return None
    if stripped == "persona":
        handle_persona()
        return None
    if stripped == "stop":
        stop_model()
        return None
    if stripped == "debug":
        return None

    # --- fallthrough: free text ---
    return handle_text(line, source=source)
