"""Event CRUD operations with recurrence expansion, backed by SQLite."""

import calendar
from datetime import datetime, timedelta

from .db import get_connection, init_db


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _next_event_id(conn) -> int:
    """Return the lowest positive integer not used by any event."""
    rows = conn.execute("SELECT id FROM events ORDER BY id").fetchall()
    used = {r[0] for r in rows}
    n = 1
    while n in used:
        n += 1
    return n


def create_event(
    title: str,
    start_time: str,
    end_time: str | None = None,
    location: str | None = None,
    notes: str | None = None,
    frequency: str | None = None,
    interval: int = 1,
    end_date: str | None = None,
) -> int:
    """Insert a new event (with optional recurrence rule) and return its id."""
    init_db()
    now = _now()
    conn = get_connection()
    try:
        event_id = _next_event_id(conn)
        conn.execute(
            "INSERT INTO events (id, title, start_time, end_time, location, notes, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, title, start_time, end_time, location, notes, now, now),
        )
        if frequency:
            conn.execute(
                "INSERT INTO recurrence_rules (event_id, frequency, interval, end_date) "
                "VALUES (?, ?, ?, ?)",
                (event_id, frequency, interval, end_date),
            )
        conn.commit()
        return event_id
    finally:
        conn.close()


def list_events() -> list[dict]:
    """Return all events with their recurrence rules."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT e.*, r.frequency, r.interval AS rec_interval, r.end_date AS rec_end_date "
            "FROM events e LEFT JOIN recurrence_rules r ON r.event_id = e.id "
            "ORDER BY e.start_time, e.id",
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_event(event_id: int) -> dict | None:
    """Return a single event by id, or None."""
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT e.*, r.frequency, r.interval AS rec_interval, r.end_date AS rec_end_date "
            "FROM events e LEFT JOIN recurrence_rules r ON r.event_id = e.id "
            "WHERE e.id = ?",
            (event_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_event(event_id: int, **fields) -> bool:
    """Update event fields. Returns True if a row was updated."""
    if not fields:
        return False
    init_db()
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [event_id]
    conn = get_connection()
    try:
        cur = conn.execute(
            f"UPDATE events SET {set_clause} WHERE id = ?", values,
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_event(event_id: int) -> bool:
    """Delete an event (and its recurrence rule via CASCADE). Returns True if deleted."""
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _add_months(dt: datetime, months: int) -> datetime:
    """Add *months* to a datetime, clamping the day to the last valid day."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, max_day)
    return dt.replace(year=year, month=month, day=day)


def _expand_recurrence(
    start: datetime,
    end: datetime | None,
    frequency: str,
    interval: int,
    rec_end: datetime | None,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[datetime, datetime | None]]:
    """Generate occurrences within [window_start, window_end].

    Returns list of (occurrence_start, occurrence_end) tuples.
    """
    duration = (end - start) if end else None
    occurrences: list[tuple[datetime, datetime | None]] = []
    current = start
    max_iter = 1000

    for _ in range(max_iter):
        if rec_end and current > rec_end:
            break
        if current > window_end:
            break

        if current >= window_start:
            occ_end = (current + duration) if duration else None
            occurrences.append((current, occ_end))

        # Advance to next occurrence
        if frequency == "daily":
            current += timedelta(days=interval)
        elif frequency == "weekly":
            current += timedelta(weeks=interval)
        elif frequency == "monthly":
            current = _add_months(current, interval)
        elif frequency == "yearly":
            current = _add_months(current, 12 * interval)
        else:
            break

    return occurrences


def get_upcoming_events(days: int = 7, limit: int = 10) -> list[dict]:
    """Return upcoming event occurrences within the next *days* days.

    Recurring events are expanded into individual occurrences.
    """
    init_db()
    now = datetime.now()
    window_start = now
    window_end = now + timedelta(days=days)

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT e.*, r.frequency, r.interval AS rec_interval, r.end_date AS rec_end_date "
            "FROM events e LEFT JOIN recurrence_rules r ON r.event_id = e.id "
            "ORDER BY e.start_time",
        ).fetchall()
    finally:
        conn.close()

    results: list[dict] = []

    for row in rows:
        event = dict(row)
        start = datetime.fromisoformat(event["start_time"])
        end = datetime.fromisoformat(event["end_time"]) if event["end_time"] else None
        freq = event.get("frequency")

        if freq:
            rec_end = (
                datetime.fromisoformat(event["rec_end_date"])
                if event.get("rec_end_date")
                else None
            )
            occurrences = _expand_recurrence(
                start, end, freq, event.get("rec_interval") or 1,
                rec_end, window_start, window_end,
            )
            for occ_start, occ_end in occurrences:
                results.append({
                    "id": event["id"],
                    "title": event["title"],
                    "start_time": occ_start.isoformat(timespec="minutes"),
                    "end_time": occ_end.isoformat(timespec="minutes") if occ_end else None,
                    "location": event["location"],
                    "notes": event["notes"],
                    "frequency": freq,
                })
        else:
            if start >= window_start and start <= window_end:
                results.append({
                    "id": event["id"],
                    "title": event["title"],
                    "start_time": event["start_time"],
                    "end_time": event["end_time"],
                    "location": event["location"],
                    "notes": event["notes"],
                    "frequency": None,
                })

    results.sort(key=lambda e: e["start_time"])
    return results[:limit]
