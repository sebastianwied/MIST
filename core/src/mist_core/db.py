"""SQLite database setup and connection."""

import sqlite3
from pathlib import Path

DB_PATH = Path("data/mist.db")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS tasks (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'todo',
    due_date   TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY,
    title      TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT,
    location   TEXT,
    notes      TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recurrence_rules (
    id        INTEGER PRIMARY KEY,
    event_id  INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    frequency TEXT NOT NULL,
    interval  INTEGER NOT NULL DEFAULT 1,
    end_date  TEXT,
    UNIQUE(event_id)
);
"""


def get_connection() -> sqlite3.Connection:
    """Return a connection to the database, creating tables if needed."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Ensure all tables exist."""
    conn = get_connection()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
