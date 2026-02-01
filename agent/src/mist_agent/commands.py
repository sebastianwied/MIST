"""Command parsing and dispatch."""

from typing import Callable

from .event_command import handle_event_add, handle_event_delete, handle_event_list
from .extraction import apply_extracted_items, extract_items
from .notes import handle_note, handle_notes, handle_recall
from .persona_command import handle_persona
from .respond import handle_text
from .settings import get_setting, load_settings, set_setting
from .summarize import handle_summarize
from .synthesis import handle_resynth, handle_sync
from .task_command import (
    handle_task_add,
    handle_task_delete,
    handle_task_done,
    handle_task_list,
)
from .types import Writer
from .util import handle_status, stop_model
from .view_command import handle_view


def _dispatch_task(sub: str, arg: str, output: Writer) -> None:
    """Route task sub-commands."""
    if sub == "add":
        handle_task_add(arg, output=output)
    elif sub in ("list", "ls"):
        handle_task_list(arg, output=output)
    elif sub == "done":
        handle_task_done(arg, output=output)
    elif sub == "delete":
        handle_task_delete(arg, output=output)
    else:
        output(f"Unknown task command '{sub}'. Try: add, list, done, delete")


def _dispatch_event(sub: str, arg: str, output: Writer) -> None:
    """Route event sub-commands."""
    if sub == "add":
        handle_event_add(arg, output=output)
    elif sub in ("list", "ls"):
        handle_event_list(arg, output=output)
    elif sub == "delete":
        handle_event_delete(arg, output=output)
    else:
        output(f"Unknown event command '{sub}'. Try: add, list, delete")


def _handle_settings(output: Writer) -> None:
    """Display all current settings."""
    settings = load_settings()
    output("Current settings:")
    for k, v in sorted(settings.items()):
        output(f"  {k} = {v}")


_HELP_TEXT = """\
Commands:
  note <text>                  Save a note (no LLM call)
  notes                        List recent notes
  recall <topic>               Search past input via LLM
  task add <title> [due:DATE]  Create a task
  task list [all] / tasks      List tasks
  task done <id>               Mark task done
  task delete <id>             Delete task
  event add <title> <date> <time>[-end] [freq] [until:date]
                               Create an event
  event list [days] / events   List upcoming events
  event delete <id>            Delete event
  sync                         Update synthesis with new themes
  resynth                      Full synthesis rewrite (deep model)
  summarize                    Summarize new entries to journal
  persona                      Edit agent personality
  view <name>                  View a file or data
  settings                     Show settings
  set <key> <value>            Change a setting
  status                       System status
  stop                         Unload model
  help                         Show this help"""


def _handle_set(arg: str, output: Writer) -> None:
    """Handle 'set <key> <value>'."""
    parts = arg.split(None, 1)
    if len(parts) < 2:
        output("Usage: set <key> <value>")
        return
    key, raw_value = parts
    # Coerce numeric values
    try:
        value = int(raw_value)
    except ValueError:
        value = raw_value
    set_setting(key, value)
    output(f"Setting '{key}' set to '{value}'.")


def dispatch(
    line: str,
    source: str = "terminal",
    output: Writer = print,
    input_fn: Callable[..., str] = input,
) -> str | None:
    """Route raw input to the appropriate handler.

    Prefix commands (note, recall, view, task, event, set) consume the rest of
    the line as an argument.
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
        handle_note(arg, output=output)
        return None
    if cmd == "recall" and arg:
        return handle_recall(arg)
    if cmd == "view":
        handle_view(arg or None, output=output)
        return None

    # --- task / event sub-command routing ---
    if cmd == "task":
        sub, _, sub_arg = arg.partition(" ")
        sub = sub.lower()
        _dispatch_task(sub, sub_arg.strip(), output)
        return None
    if cmd == "event":
        sub, _, sub_arg = arg.partition(" ")
        sub = sub.lower()
        _dispatch_event(sub, sub_arg.strip(), output)
        return None

    # --- settings ---
    if cmd == "set" and arg:
        _handle_set(arg, output=output)
        return None

    # --- bare commands ---
    if stripped == "tasks":
        handle_task_list("", output=output)
        return None
    if stripped == "events":
        handle_event_list("", output=output)
        return None
    if stripped == "settings":
        _handle_settings(output=output)
        return None
    if stripped == "notes":
        handle_notes(output=output)
        return None
    if stripped == "sync":
        handle_sync(output=output)
        return None
    if stripped == "resynth":
        handle_resynth(output=output)
        return None
    if stripped == "summarize":
        handle_summarize(output=output)
        return None
    if stripped == "status":
        handle_status(output=output)
        return None
    if stripped == "persona":
        handle_persona(output=output, input_fn=input_fn)
        return None
    if stripped == "stop":
        stop_model()
        return None
    if stripped == "help":
        output(_HELP_TEXT)
        return None
    if stripped == "debug":
        return None

    # --- fallthrough: free text ---
    response = handle_text(line, source=source)

    # --- LLM extraction ---
    agency_mode = get_setting("agency_mode")
    if agency_mode != "off":
        items = extract_items(line)
        has_items = items.get("tasks") or items.get("events")
        if has_items:
            if agency_mode == "auto":
                output("(auto-creating detected items)")
                apply_extracted_items(items, output=output)
            elif agency_mode == "suggest":
                def _confirm(prompt_text: str) -> bool:
                    try:
                        ans = input_fn(f"  {prompt_text} [y/N] ")
                        return ans.strip().lower() in ("y", "yes")
                    except (EOFError, KeyboardInterrupt):
                        return False
                output("Detected tasks/events in your message:")
                apply_extracted_items(items, output=output, confirm_fn=_confirm)

    return response
