"""Task CRUD operations backed by SQLite."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..db import Database


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TaskStore:
    """Task storage backed by a shared Database instance."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _next_id(self) -> int:
        """Return the lowest positive integer not used by an active task."""
        rows = self.db.conn.execute(
            "SELECT id FROM tasks WHERE status = 'todo' ORDER BY id"
        ).fetchall()
        used = {r[0] for r in rows}
        n = 1
        while n in used:
            n += 1
        return n

    def create(self, title: str, due_date: str | None = None) -> int:
        """Insert a new task and return its id."""
        now = _now()
        task_id = self._next_id()
        self.db.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.db.conn.execute(
            "INSERT INTO tasks (id, title, status, due_date, created_at, updated_at) "
            "VALUES (?, ?, 'todo', ?, ?, ?)",
            (task_id, title, due_date, now, now),
        )
        self.db.conn.commit()
        return task_id

    def list(self, include_done: bool = False) -> list[dict]:
        """Return tasks as dicts. By default only open (todo) tasks."""
        if include_done:
            rows = self.db.conn.execute(
                "SELECT * FROM tasks ORDER BY due_date IS NULL, due_date, id",
            ).fetchall()
        else:
            rows = self.db.conn.execute(
                "SELECT * FROM tasks WHERE status = 'todo' "
                "ORDER BY due_date IS NULL, due_date, id",
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, task_id: int) -> dict | None:
        """Return a single task by id, or None."""
        row = self.db.conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None

    def update(self, task_id: int, **fields) -> bool:
        """Update task fields. Returns True if a row was updated."""
        if not fields:
            return False
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        cur = self.db.conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?", values,
        )
        self.db.conn.commit()
        return cur.rowcount > 0

    def delete(self, task_id: int) -> bool:
        """Delete a task. Returns True if a row was deleted."""
        cur = self.db.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.db.conn.commit()
        return cur.rowcount > 0

    def get_upcoming(self, days: int = 7, limit: int = 10) -> list[dict]:
        """Return open tasks due within the next *days* days, plus undated."""
        cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        rows = self.db.conn.execute(
            "SELECT * FROM tasks WHERE status = 'todo' "
            "AND (due_date IS NULL OR due_date <= ?) "
            "ORDER BY due_date IS NULL, due_date, id "
            "LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]
