"""Task CRUD operations backed by SQLite."""

from datetime import datetime, timedelta

from .db import get_connection, init_db


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_task(title: str, due_date: str | None = None) -> int:
    """Insert a new task and return its id."""
    init_db()
    now = _now()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO tasks (title, status, due_date, created_at, updated_at) "
            "VALUES (?, 'todo', ?, ?, ?)",
            (title, due_date, now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_tasks(include_done: bool = False) -> list[dict]:
    """Return tasks as dicts. By default only open (todo) tasks."""
    init_db()
    conn = get_connection()
    try:
        if include_done:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY due_date IS NULL, due_date, id",
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'todo' "
                "ORDER BY due_date IS NULL, due_date, id",
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_task(task_id: int) -> dict | None:
    """Return a single task by id, or None."""
    init_db()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_task(task_id: int, **fields) -> bool:
    """Update task fields. Returns True if a row was updated."""
    if not fields:
        return False
    init_db()
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [task_id]
    conn = get_connection()
    try:
        cur = conn.execute(
            f"UPDATE tasks SET {set_clause} WHERE id = ?", values,
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_task(task_id: int) -> bool:
    """Delete a task. Returns True if a row was deleted."""
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_upcoming_tasks(days: int = 7, limit: int = 10) -> list[dict]:
    """Return open tasks due within the next *days* days, plus undated tasks."""
    init_db()
    cutoff = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'todo' "
            "AND (due_date IS NULL OR due_date <= ?) "
            "ORDER BY due_date IS NULL, due_date, id "
            "LIMIT ?",
            (cutoff, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
