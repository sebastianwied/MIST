"""Handlers for the 'task' command family."""

import re
from datetime import datetime

from mist_core.task_store import create_task, delete_task, list_tasks, update_task
from mist_core.types import Writer

_DUE_RE = re.compile(r"\s+due:(\S+)")


def _parse_due(arg: str) -> tuple[str, str | None]:
    """Extract and remove a due:YYYY-MM-DD suffix from the argument string."""
    m = _DUE_RE.search(arg)
    if m:
        return _DUE_RE.sub("", arg).strip(), m.group(1)
    return arg.strip(), None


def _format_task(t: dict) -> str:
    """Format a single task for display."""
    status_icon = {"todo": " ", "done": "x", "cancelled": "-"}.get(t["status"], "?")
    due = ""
    if t.get("due_date"):
        try:
            day = datetime.fromisoformat(t["due_date"]).strftime("%a")
            due = f"  (due {t['due_date']}, {day})"
        except ValueError:
            due = f"  (due {t['due_date']})"
    return f"  [{status_icon}] #{t['id']}  {t['title']}{due}"


def handle_task_add(arg: str, output: Writer = print) -> None:
    """Create a new task from the argument string."""
    if not arg:
        output("Usage: task add <title> [due:YYYY-MM-DD]")
        return
    title, due_date = _parse_due(arg)
    task_id = create_task(title, due_date=due_date)
    due_msg = f" (due {due_date})" if due_date else ""
    output(f"Task #{task_id} created: {title}{due_msg}")


def handle_task_list(arg: str, output: Writer = print) -> None:
    """List tasks. 'task list all' includes done/cancelled."""
    include_done = arg.strip().lower() == "all"
    tasks = list_tasks(include_done=include_done)
    if not tasks:
        label = "No tasks." if include_done else "No open tasks."
        output(label)
        return
    for t in tasks:
        output(_format_task(t))


def handle_task_done(arg: str, output: Writer = print) -> None:
    """Mark a task as done by id."""
    try:
        task_id = int(arg.strip())
    except (ValueError, AttributeError):
        output("Usage: task done <id>")
        return
    if update_task(task_id, status="done"):
        output(f"Task #{task_id} marked done.")
    else:
        output(f"Task #{task_id} not found.")


def handle_task_delete(arg: str, output: Writer = print) -> None:
    """Delete a task by id."""
    try:
        task_id = int(arg.strip())
    except (ValueError, AttributeError):
        output("Usage: task delete <id>")
        return
    if delete_task(task_id):
        output(f"Task #{task_id} deleted.")
    else:
        output(f"Task #{task_id} not found.")
