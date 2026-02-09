"""Article CRUD operations backed by SQLite."""

from __future__ import annotations

import json
from datetime import datetime

from ..db import Database


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ArticleStore:
    """Article storage backed by a shared Database instance."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(
        self,
        title: str,
        authors: list[str],
        abstract: str | None = None,
        year: int | None = None,
        source_url: str | None = None,
        arxiv_id: str | None = None,
        s2_id: str | None = None,
    ) -> int:
        """Insert a new article and return its id."""
        now = _now()
        cur = self.db.conn.execute(
            "INSERT INTO articles "
            "(title, authors, abstract, year, source_url, arxiv_id, s2_id, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, json.dumps(authors), abstract, year, source_url,
             arxiv_id, s2_id, now, now),
        )
        self.db.conn.commit()
        return cur.lastrowid

    def get(self, article_id: int) -> dict | None:
        """Return a single article by id with its tags, or None."""
        row = self.db.conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,),
        ).fetchone()
        if not row:
            return None
        article = dict(row)
        article["authors"] = json.loads(article["authors"])
        tags = self.db.conn.execute(
            "SELECT tag FROM article_tags WHERE article_id = ? ORDER BY tag",
            (article_id,),
        ).fetchall()
        article["tags"] = [t[0] for t in tags]
        return article

    def list(self, tag: str | None = None) -> list[dict]:
        """Return articles as dicts. Optionally filter by tag."""
        if tag:
            rows = self.db.conn.execute(
                "SELECT a.* FROM articles a "
                "JOIN article_tags t ON a.id = t.article_id "
                "WHERE t.tag = ? ORDER BY a.created_at DESC",
                (tag,),
            ).fetchall()
        else:
            rows = self.db.conn.execute(
                "SELECT * FROM articles ORDER BY created_at DESC",
            ).fetchall()
        result = []
        for row in rows:
            article = dict(row)
            article["authors"] = json.loads(article["authors"])
            tags = self.db.conn.execute(
                "SELECT tag FROM article_tags WHERE article_id = ? ORDER BY tag",
                (article["id"],),
            ).fetchall()
            article["tags"] = [t[0] for t in tags]
            result.append(article)
        return result

    def update(self, article_id: int, **fields) -> bool:
        """Update article fields. Returns True if a row was updated."""
        if not fields:
            return False
        if "authors" in fields and isinstance(fields["authors"], list):
            fields["authors"] = json.dumps(fields["authors"])
        fields["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [article_id]
        cur = self.db.conn.execute(
            f"UPDATE articles SET {set_clause} WHERE id = ?", values,
        )
        self.db.conn.commit()
        return cur.rowcount > 0

    def delete(self, article_id: int) -> bool:
        """Delete an article. Returns True if a row was deleted."""
        cur = self.db.conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        self.db.conn.commit()
        return cur.rowcount > 0

    def add_tag(self, article_id: int, tag: str) -> None:
        """Add a tag to an article."""
        self.db.conn.execute(
            "INSERT OR IGNORE INTO article_tags (article_id, tag) VALUES (?, ?)",
            (article_id, tag),
        )
        self.db.conn.commit()

    def remove_tag(self, article_id: int, tag: str) -> None:
        """Remove a tag from an article."""
        self.db.conn.execute(
            "DELETE FROM article_tags WHERE article_id = ? AND tag = ?",
            (article_id, tag),
        )
        self.db.conn.commit()

    def list_tags(self) -> list[str]:
        """Return all distinct tags."""
        rows = self.db.conn.execute(
            "SELECT DISTINCT tag FROM article_tags ORDER BY tag",
        ).fetchall()
        return [r[0] for r in rows]
