"""Entry points for the MIST agent."""

import sys
import threading
from contextlib import contextmanager

from .commands import dispatch

_SPINNER_CHARS = "|/-\\"


@contextmanager
def _spinner(msg: str = "Thinking..."):
    """Display a cycling spinner on the current line while the body runs."""
    stop = threading.Event()

    def _spin():
        i = 0
        while not stop.is_set():
            ch = _SPINNER_CHARS[i % len(_SPINNER_CHARS)]
            sys.stdout.write(f"\r  {ch} {msg}")
            sys.stdout.flush()
            i += 1
            stop.wait(0.12)
        # clear the spinner line
        sys.stdout.write("\r" + " " * (len(msg) + 6) + "\r")
        sys.stdout.flush()

    t = threading.Thread(target=_spin, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join()


# Commands that call the LLM and should show a spinner
_LLM_COMMANDS = {
    "recall": "Recalling...",
    "aggregate": "Aggregating...",
    "sync": "Synthesizing...",
    "resynth": "Resynthesizing...",
    "synthesis": "Synthesizing topic...",
    "persona": "Generating persona...",
}

_NO_SPINNER_COMMANDS = {
    "task", "event", "note", "notes", "view", "status",
    "settings", "set", "help", "stop", "tasks", "events", "debug",
}


def _spinner_label(line: str) -> str | None:
    """Return a spinner label for the command, or None to skip the spinner."""
    cmd = line.split()[0].lower() if line.split() else ""
    if cmd in _LLM_COMMANDS:
        return _LLM_COMMANDS[cmd]
    if cmd in _NO_SPINNER_COMMANDS:
        return None
    return "Thinking..."


def repl() -> None:
    """Run the interactive read-eval-print loop (plain terminal fallback)."""
    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue
            if line in {"exit", "quit"}:
                break

            label = _spinner_label(line)
            if label:
                with _spinner(label):
                    result = dispatch(line)
            else:
                result = dispatch(line)

            if result is not None:
                print(result)

        except KeyboardInterrupt:
            print("\nExiting.")
            break


def tui() -> None:
    """Launch the Textual TUI."""
    from .tui import MistApp

    MistApp().run()


if __name__ == "__main__":
    repl()
