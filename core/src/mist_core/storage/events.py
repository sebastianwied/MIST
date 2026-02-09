"""Event CRUD operations with recurrence expansion, backed by SQLite."""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from ..db import Database


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class EventStore:
    """Event storage backed by a shared Database instance."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _next_id(self) -> int:
        rows = self.db.conn.execute("SELECT id FROM events ORDER BY id").fetchall()
        used = {r[0] for r in rows}
        n = 1
        while n in used:
            n += 1
        return n

    def create(
        self,
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
        now = _now()
        event_id = self._next_id()
        self.db.conn.execute(
            "INSERT INTO events (id, title, start_time, end_time, location, notes, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, title, start_time, end_time, location, notes, now, now),
        )
        if frequency:
            self.db.conn.execute(
                "INSERT INTO recurrence_rules (event_id, frequency, interval, end_date) "
                "VALUES (?, ?, ?, ?)",
                (event_id, frequency, interval, end_date),
            )
        self.db.conn.commit()
        return event_id

    def list(self) -> list[dict]:
        """Return all events with their recurrence rules."""
        rows = self.db.conn.execute(
            "SELECT e.*, r.frequency, r.interval AS rec_interval, r.end_date AS rec_end_date "
            "FROM events e LEFT JOIN recurrence_rules r ON r.event_id = e.id "
            "ORDER BY e.start_time, e.id",
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, event_id: int) -> dict | None:
        """Return a single event by id, or None."""
        row = self.db.conn.execute(
            "SELECT e.*, r.frequency, r.interval AS rec_interval, r.end_date AS rec_end_date "
            "FROM events e LEFT JOIN recurrence_rules r ON r.event_id = e.id "
            "WHERE e.id = ?",
            (event_id,),
        ).fetchone()
        return dict(row) if row else None

    def update(self, event_id: int, **fields) -> bool:
        """Update event fields. Returns True if a row was updated."""
        if not fields:
            return False
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [event_id]
        cur = self.db.conn.execute(
            f"UPDATE events SET {set_clause} WHERE id = ?", values,
        )
        self.db.conn.commit()
        return cur.rowcount > 0

    def delete(self, event_id: int) -> bool:
        """Delete an event (and its recurrence rule via CASCADE)."""
        cur = self.db.conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        self.db.conn.commit()
        return cur.rowcount > 0

    def get_upcoming(self, days: int = 7, limit: int = 10) -> list[dict]:
        """Return upcoming event occurrences within the next *days* days.

        Recurring events are expanded into individual occurrences.
        """
        now = datetime.now()
        window_start = now
        window_end = now + timedelta(days=days)

        rows = self.db.conn.execute(
            "SELECT e.*, r.frequency, r.interval AS rec_interval, r.end_date AS rec_end_date "
            "FROM events e LEFT JOIN recurrence_rules r ON r.event_id = e.id "
            "ORDER BY e.start_time",
        ).fetchall()

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
                if window_start <= start <= window_end:
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


# ── Recurrence helpers ──────────────────────────────────────────────


def _add_months(dt: datetime, months: int) -> datetime:
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
    """Generate occurrences within [window_start, window_end]."""
    duration = (end - start) if end else None
    occurrences: list[tuple[datetime, datetime | None]] = []
    current = start

    for _ in range(1000):
        if rec_end and current > rec_end:
            break
        if current > window_end:
            break
        if current >= window_start:
            occ_end = (current + duration) if duration else None
            occurrences.append((current, occ_end))
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
