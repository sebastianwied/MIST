"""Handlers for the 'event' command family."""

import re
from datetime import datetime

from mist_core.event_store import create_event, delete_event, get_upcoming_events
from mist_core.types import Writer

# event add <title> <date> <time>[-<end_time>] [weekly|daily|monthly|yearly] [until:YYYY-MM-DD]
_UNTIL_RE = re.compile(r"\s+until:(\S+)")
_TIME_RANGE_RE = re.compile(r"(\d{1,2}:\d{2})(?:-(\d{1,2}:\d{2}))?")
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_FREQ_WORDS = {"daily", "weekly", "monthly", "yearly"}


def _parse_event_args(arg: str) -> dict | None:
    """Parse event add arguments into a dict of fields.

    Expected format:
        <title> <YYYY-MM-DD> <HH:MM>[-HH:MM] [frequency] [until:YYYY-MM-DD]
    """
    # Extract until:date
    until = None
    m_until = _UNTIL_RE.search(arg)
    if m_until:
        until = m_until.group(1)
        arg = _UNTIL_RE.sub("", arg).strip()

    # Extract frequency
    tokens = arg.split()
    frequency = None
    remaining_tokens = []
    for tok in tokens:
        if tok.lower() in _FREQ_WORDS:
            frequency = tok.lower()
        else:
            remaining_tokens.append(tok)
    arg = " ".join(remaining_tokens)

    # Extract date
    m_date = _DATE_RE.search(arg)
    if not m_date:
        return None
    date_str = m_date.group(1)

    # Extract time range
    # Look for time after the date
    after_date = arg[m_date.end():]
    m_time = _TIME_RANGE_RE.search(after_date)
    if not m_time:
        return None
    start_hm = m_time.group(1)
    end_hm = m_time.group(2)

    # Title is everything before the date
    title = arg[:m_date.start()].strip()
    if not title:
        return None

    start_time = f"{date_str}T{start_hm}"
    end_time = f"{date_str}T{end_hm}" if end_hm else None

    return {
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "frequency": frequency,
        "end_date": until,
    }


def _format_time(iso: str) -> str:
    """Format an ISO datetime string for display."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%b %-d %a, %H:%M")
    except (ValueError, TypeError):
        return iso


def _format_event(e: dict) -> str:
    """Format a single event occurrence for display."""
    time_str = _format_time(e["start_time"])
    if e.get("end_time"):
        end_dt = datetime.fromisoformat(e["end_time"])
        time_str += f"-{end_dt.strftime('%H:%M')}"
    freq = f"  ({e['frequency']})" if e.get("frequency") else ""
    loc = f"  @ {e['location']}" if e.get("location") else ""
    return f"  #{e['id']}  {e['title']}  —  {time_str}{freq}{loc}"


def handle_event_add(arg: str, output: Writer = print) -> None:
    """Create a new event from the argument string."""
    if not arg:
        output("Usage: event add <title> <YYYY-MM-DD> <HH:MM>[-HH:MM] [weekly|daily|monthly|yearly] [until:YYYY-MM-DD]")
        return
    parsed = _parse_event_args(arg)
    if not parsed:
        output("Could not parse event. Expected: event add <title> <YYYY-MM-DD> <HH:MM>[-HH:MM] [frequency] [until:date]")
        return
    event_id = create_event(
        title=parsed["title"],
        start_time=parsed["start_time"],
        end_time=parsed["end_time"],
        frequency=parsed.get("frequency"),
        end_date=parsed.get("end_date"),
    )
    freq_msg = f" ({parsed['frequency']})" if parsed.get("frequency") else ""
    output(f"Event #{event_id} created: {parsed['title']} at {parsed['start_time']}{freq_msg}")


def handle_event_list(arg: str, output: Writer = print) -> None:
    """List upcoming events. Optional argument: number of days (default 7)."""
    days = 7
    if arg.strip():
        try:
            days = int(arg.strip())
        except ValueError:
            output("Usage: event list [days]")
            return
    events = get_upcoming_events(days=days)
    if not events:
        output(f"No events in the next {days} days.")
        return
    output(f"Events (next {days} days):")
    for e in events:
        output(_format_event(e))


def handle_event_delete(arg: str, output: Writer = print) -> None:
    """Delete an event by id."""
    try:
        event_id = int(arg.strip())
    except (ValueError, AttributeError):
        output("Usage: event delete <id>")
        return
    if delete_event(event_id):
        output(f"Event #{event_id} deleted.")
    else:
        output(f"Event #{event_id} not found.")
