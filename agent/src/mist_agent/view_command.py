"""Handler for the 'view' command — display config and data files."""

from pathlib import Path

from .settings import get_model, MODEL_COMMANDS
from .storage import CONTEXT_PATH, RAWLOG_PATH, load_topic_about, load_topic_files, load_topic_index
from .task_command import handle_task_list
from .event_command import handle_event_list
from .types import Writer

VIEWABLE_FILES: dict[str, Path] = {
    "persona": Path("data/config/persona.md"),
    "user": Path("data/config/user.md"),
    "rawlog": RAWLOG_PATH,
    "context": CONTEXT_PATH,
}

# Keys that are handled specially (not simple file reads).
_VIRTUAL_KEYS = {"synthesis", "tasks", "events", "topics", "model"}

# All file-backed keys (excludes virtual keys) — safe to open in an editor.
EDITABLE_FILES: set[str] = set(VIEWABLE_FILES)

# Files whose entries should be shown most-recent-first.
_REVERSE_CHRONOLOGICAL = {"rawlog"}


def _reverse_content(key: str, content: str) -> str:
    """Reverse chronological entries for rawlog (JSONL: reverse lines)."""
    if key == "rawlog":
        lines = [l for l in content.splitlines() if l.strip()]
        return "\n".join(reversed(lines))
    return content


def _all_viewable_keys() -> list[str]:
    """Return sorted list of all viewable keys (files + virtual)."""
    return sorted(set(VIEWABLE_FILES) | _VIRTUAL_KEYS)


def _show_model(output: Writer) -> None:
    """Display the default model, its source, and per-command overrides."""
    from .ollama_client import _load_model_conf
    from .settings import load_settings

    settings = load_settings()
    default = get_model()

    # Determine source of the default
    settings_model = settings.get("model", "")
    conf_model = _load_model_conf()
    if settings_model:
        source = "settings.json"
    elif conf_model:
        source = "model.conf"
    else:
        source = "built-in default"

    output(f"Default model: {default}  (source: {source})")
    output("")
    output("Per-command models:")
    for cmd in MODEL_COMMANDS:
        key = f"model_{cmd}"
        override = settings.get(key, "")
        resolved = get_model(cmd)
        if override:
            output(f"  {cmd:12s}  {override}")
        else:
            output(f"  {cmd:12s}  ({resolved})")


def handle_view(name: str | None, output: Writer = print) -> None:
    """Display a viewable file. With no argument, list available names."""
    if name is None:
        output("Viewable files: " + ", ".join(_all_viewable_keys()))
        return

    key = name.lower()

    # Virtual key: model — show resolution table
    if key == "model":
        _show_model(output)
        return

    # Virtual key: synthesis — concatenate all topic synthesis files
    if key == "synthesis":
        topics = load_topic_files()
        if not topics:
            output("No synthesis topics yet. Run 'aggregate' then 'sync' first.")
            return
        output("\n\n".join(
            f"## {slug}\n{content}" for slug, content in topics.items()
        ))
        return

    # Virtual key: topics — list topic index with descriptions
    if key == "topics":
        index = load_topic_index()
        if not index:
            output("No topics yet. Run 'aggregate' first.")
            return
        output("Topics:")
        for t in index:
            about = load_topic_about(t.slug)
            desc = f" — {about}" if about else ""
            output(f"  [{t.id}] {t.slug}: {t.name}{desc}")
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
