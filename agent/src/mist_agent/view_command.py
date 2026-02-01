"""Handler for the 'view' command — display config and data files."""

import re
from pathlib import Path

from .storage import CONTEXT_PATH, load_topic_files
from .task_command import handle_task_list
from .event_command import handle_event_list
from .types import Writer

VIEWABLE_FILES: dict[str, Path] = {
    "persona": Path("data/config/persona.md"),
    "user": Path("data/config/user.md"),
    "model": Path("data/config/model.conf"),
    "rawlog": Path("data/notes/rawLog.md"),
    "journal": Path("data/agentJournal.md"),
    "context": CONTEXT_PATH,
}

# Keys that are handled specially (not simple file reads).
_VIRTUAL_KEYS = {"synthesis", "tasks", "events"}

# Files whose entries should be shown most-recent-first.
_REVERSE_CHRONOLOGICAL = {"rawlog", "journal"}

_RAWLOG_SPLIT = re.compile(r"(?=\n---\s*\ntime:)")
_JOURNAL_SPLIT = re.compile(r"(?=\n## )")


def _reverse_content(key: str, content: str) -> str:
    """Reverse chronological entries for rawlog and journal files."""
    if key == "rawlog":
        parts = _RAWLOG_SPLIT.split(content)
    elif key == "journal":
        parts = _JOURNAL_SPLIT.split(content)
    else:
        return content
    parts = [p.strip() for p in parts if p.strip()]
    return "\n\n".join(reversed(parts))


def _all_viewable_keys() -> list[str]:
    """Return sorted list of all viewable keys (files + virtual)."""
    return sorted(set(VIEWABLE_FILES) | _VIRTUAL_KEYS)


def handle_view(name: str | None, output: Writer = print) -> None:
    """Display a viewable file. With no argument, list available names."""
    if name is None:
        output("Viewable files: " + ", ".join(_all_viewable_keys()))
        return

    key = name.lower()

    # Virtual key: synthesis — concatenate all topic files
    if key == "synthesis":
        topics = load_topic_files()
        if not topics:
            output("No synthesis topics yet. Run 'sync' first.")
            return
        output("\n\n".join(topics.values()))
        return

    # Virtual key: tasks
    if key == "tasks":
        handle_task_list("all", output=output)
        return

    # Virtual key: events
    if key == "events":
        handle_event_list("30", output=output)
        return

    path = VIEWABLE_FILES.get(key)
    if path is None:
        output(f"Unknown file '{name}'. Available: {', '.join(_all_viewable_keys())}")
        return

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        output(f"{path} not found.")
        return

    if key in _REVERSE_CHRONOLOGICAL:
        content = _reverse_content(key, content)

    output(content)
