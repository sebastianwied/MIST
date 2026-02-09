"""Tests for mist_core.db."""

import pytest

from mist_core.db import Database, CURRENT_SCHEMA_VERSION


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.connect()
    database.init_schema()
    yield database
    database.close()


class TestDatabase:
    def test_creates_db_file(self, tmp_path):
        db = Database(tmp_path / "sub" / "test.db")
        db.connect()
        db.init_schema()
        assert (tmp_path / "sub" / "test.db").exists()
        db.close()

    def test_schema_version(self, db):
        assert db.schema_version == CURRENT_SCHEMA_VERSION

    def test_tables_exist(self, db):
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r[0] for r in tables}
        assert "tasks" in names
        assert "events" in names
        assert "recurrence_rules" in names
        assert "articles" in names
        assert "article_tags" in names
        assert "schema_version" in names

    def test_foreign_keys_enabled(self, db):
        row = db.conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1

    def test_init_schema_idempotent(self, db):
        db.init_schema()
        db.init_schema()
        assert db.schema_version == CURRENT_SCHEMA_VERSION

    def test_conn_raises_before_connect(self, tmp_path):
        db = Database(tmp_path / "test.db")
        with pytest.raises(RuntimeError, match="connect"):
            _ = db.conn
