"""SQLite database setup and connection, class-based."""

import sqlite3
from pathlib import Path

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

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

CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    authors     TEXT NOT NULL,
    abstract    TEXT,
    year        INTEGER,
    source_url  TEXT,
    arxiv_id    TEXT,
    s2_id       TEXT,
    pdf_path    TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_tags (
    article_id  INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (article_id, tag)
);
"""

CURRENT_SCHEMA_VERSION = 1


class Database:
    """SQLite database wrapper.

    Usage:
        db = Database(paths.db)
        db.connect()
        db.init_schema()
        ...
        db.close()
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        """Open the database connection, creating the file if needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.row_factory = sqlite3.Row

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("call connect() first")
        return self._conn

    def init_schema(self) -> None:
        """Create all tables if they don't exist and record schema version."""
        self.conn.executescript(_SCHEMA)
        row = self.conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()
        if row[0] == 0:
            self.conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (CURRENT_SCHEMA_VERSION,),
            )
        self.conn.commit()

    @property
    def schema_version(self) -> int:
        row = self.conn.execute("SELECT version FROM schema_version").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
