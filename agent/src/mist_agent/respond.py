"""Handler for free-text reflection input."""

from datetime import datetime

from mist_core.event_store import get_upcoming_events
from mist_core.ollama_client import call_ollama
from mist_core.settings import get_setting
from mist_core.storage import load_context, save_raw_input
from mist_core.task_store import get_upcoming_tasks

from .persona import load_persona
from .profile import load_user_profile
from .prompts import SYSTEM_PROMPT, USER_PROMPT


def _format_date_short(iso: str) -> str:
    """Format an ISO date or datetime string for display (e.g. 'Feb 5')."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %-d")
    except (ValueError, TypeError):
        return iso


def _format_time_short(iso: str) -> str:
    """Format an ISO datetime to 'Feb 5, 14:00'."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %-d, %H:%M")
    except (ValueError, TypeError):
        return iso


def load_schedule_context() -> str:
    """Build a short text block of upcoming tasks and events for the system prompt."""
    task_days = get_setting("context_tasks_days") or 7
    event_days = get_setting("context_events_days") or 3

    tasks = get_upcoming_tasks(days=task_days, limit=10)
    events = get_upcoming_events(days=event_days, limit=10)

    if not tasks and not events:
        return ""

    parts = ["--- UPCOMING SCHEDULE ---"]

    if tasks:
        parts.append("Tasks due soon:")
        for t in tasks:
            due = f" (due {_format_date_short(t['due_date'])})" if t.get("due_date") else ""
            parts.append(f"- {t['title']}{due}")

    if events:
        if tasks:
            parts.append("")
        parts.append("Upcoming events:")
        for e in events:
            time_str = _format_time_short(e["start_time"])
            if e.get("end_time"):
                end_dt = datetime.fromisoformat(e["end_time"])
                time_str += f"-{end_dt.strftime('%H:%M')}"
            freq = f", {e['frequency']}" if e.get("frequency") else ""
            parts.append(f"- {e['title']} ({time_str}{freq})")

    parts.append("--------------------------")
    return "\n".join(parts)


def handle_text(text: str, source: str = "terminal") -> str:
    """Log the input and return a reflective response from Ollama."""
    save_raw_input(text, source=source)
    persona = load_persona()
    user_profile = load_user_profile()
    context = load_context()

    schedule = load_schedule_context()
    if schedule:
        context = f"{context}\n\n{schedule}" if context else schedule

    system = SYSTEM_PROMPT.format(
        persona=persona, user_profile=user_profile, context=context,
    )
    prompt = USER_PROMPT.format(text=text)
    return call_ollama(prompt, system=system, command="reflect")
