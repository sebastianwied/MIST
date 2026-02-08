"""Article CRUD operations backed by SQLite."""

import json
from datetime import datetime

from .db import get_connection, init_db


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def create_article(
    title: str,
    authors: list[str],
    abstract: str | None = None,
    year: int | None = None,
    source_url: str | None = None,
    arxiv_id: str | None = None,
    s2_id: str | None = None,
) -> int:
    """Insert a new article and return its id."""
    init_db()
    now = _now()
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO articles "
            "(title, authors, abstract, year, source_url, arxiv_id, s2_id, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (title, json.dumps(authors), abstract, year, source_url,
             arxiv_id, s2_id, now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_article(article_id: int) -> dict | None:
    """Return a single article by id with its tags, or None."""
    init_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,),
        ).fetchone()
        if not row:
            return None
        article = dict(row)
        article["authors"] = json.loads(article["authors"])
        tags = conn.execute(
            "SELECT tag FROM article_tags WHERE article_id = ? ORDER BY tag",
            (article_id,),
        ).fetchall()
        article["tags"] = [t[0] for t in tags]
        return article
    finally:
        conn.close()


def list_articles(tag: str | None = None) -> list[dict]:
    """Return articles as dicts. Optionally filter by tag."""
    init_db()
    conn = get_connection()
    try:
        if tag:
            rows = conn.execute(
                "SELECT a.* FROM articles a "
                "JOIN article_tags t ON a.id = t.article_id "
                "WHERE t.tag = ? ORDER BY a.created_at DESC",
                (tag,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM articles ORDER BY created_at DESC",
            ).fetchall()
        result = []
        for row in rows:
            article = dict(row)
            article["authors"] = json.loads(article["authors"])
            tags = conn.execute(
                "SELECT tag FROM article_tags WHERE article_id = ? ORDER BY tag",
                (article["id"],),
            ).fetchall()
            article["tags"] = [t[0] for t in tags]
            result.append(article)
        return result
    finally:
        conn.close()


def delete_article(article_id: int) -> bool:
    """Delete an article. Returns True if a row was deleted."""
    init_db()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def update_article(article_id: int, **fields) -> bool:
    """Update article fields. Returns True if a row was updated."""
    if not fields:
        return False
    init_db()
    # Serialize authors list if present
    if "authors" in fields and isinstance(fields["authors"], list):
        fields["authors"] = json.dumps(fields["authors"])
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [article_id]
    conn = get_connection()
    try:
        cur = conn.execute(
            f"UPDATE articles SET {set_clause} WHERE id = ?", values,
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_pdf_path(article_id: int, path: str) -> bool:
    """Set the PDF path for an article."""
    return update_article(article_id, pdf_path=path)


def add_tag(article_id: int, tag: str) -> None:
    """Add a tag to an article."""
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO article_tags (article_id, tag) VALUES (?, ?)",
            (article_id, tag),
        )
        conn.commit()
    finally:
        conn.close()


def remove_tag(article_id: int, tag: str) -> None:
    """Remove a tag from an article."""
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM article_tags WHERE article_id = ? AND tag = ?",
            (article_id, tag),
        )
        conn.commit()
    finally:
        conn.close()


def list_tags() -> list[str]:
    """Return all distinct tags."""
    init_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT tag FROM article_tags ORDER BY tag",
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()
