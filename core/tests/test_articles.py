"""Tests for mist_core.storage.articles."""

import pytest

from mist_core.db import Database
from mist_core.storage.articles import ArticleStore


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.connect()
    database.init_schema()
    yield database
    database.close()


@pytest.fixture
def articles(db):
    return ArticleStore(db)


class TestArticleCRUD:
    def test_create_and_get(self, articles):
        aid = articles.create("Attention Is All You Need", ["Vaswani", "et al."])
        article = articles.get(aid)
        assert article is not None
        assert article["title"] == "Attention Is All You Need"
        assert article["authors"] == ["Vaswani", "et al."]
        assert article["tags"] == []

    def test_create_with_all_fields(self, articles):
        aid = articles.create(
            "Test Paper",
            ["Author A"],
            abstract="An abstract",
            year=2024,
            source_url="https://example.com",
            arxiv_id="2401.00001",
            s2_id="abc123",
        )
        article = articles.get(aid)
        assert article["abstract"] == "An abstract"
        assert article["year"] == 2024
        assert article["arxiv_id"] == "2401.00001"

    def test_list(self, articles):
        articles.create("Paper A", ["Author A"])
        articles.create("Paper B", ["Author B"])
        result = articles.list()
        assert len(result) == 2

    def test_update(self, articles):
        aid = articles.create("Original", ["Author"])
        articles.update(aid, title="Updated")
        article = articles.get(aid)
        assert article["title"] == "Updated"

    def test_update_authors(self, articles):
        aid = articles.create("Paper", ["Old Author"])
        articles.update(aid, authors=["New Author"])
        article = articles.get(aid)
        assert article["authors"] == ["New Author"]

    def test_delete(self, articles):
        aid = articles.create("To delete", ["Author"])
        assert articles.delete(aid)
        assert articles.get(aid) is None

    def test_get_nonexistent(self, articles):
        assert articles.get(999) is None


class TestTags:
    def test_add_tag(self, articles):
        aid = articles.create("Paper", ["Author"])
        articles.add_tag(aid, "ml")
        article = articles.get(aid)
        assert "ml" in article["tags"]

    def test_add_duplicate_tag(self, articles):
        aid = articles.create("Paper", ["Author"])
        articles.add_tag(aid, "ml")
        articles.add_tag(aid, "ml")  # no error
        article = articles.get(aid)
        assert article["tags"] == ["ml"]

    def test_remove_tag(self, articles):
        aid = articles.create("Paper", ["Author"])
        articles.add_tag(aid, "ml")
        articles.remove_tag(aid, "ml")
        article = articles.get(aid)
        assert article["tags"] == []

    def test_list_tags(self, articles):
        a1 = articles.create("Paper A", ["Author"])
        a2 = articles.create("Paper B", ["Author"])
        articles.add_tag(a1, "ml")
        articles.add_tag(a1, "nlp")
        articles.add_tag(a2, "ml")
        tags = articles.list_tags()
        assert tags == ["ml", "nlp"]

    def test_filter_by_tag(self, articles):
        a1 = articles.create("ML Paper", ["Author"])
        a2 = articles.create("NLP Paper", ["Author"])
        articles.add_tag(a1, "ml")
        articles.add_tag(a2, "nlp")
        ml_papers = articles.list(tag="ml")
        assert len(ml_papers) == 1
        assert ml_papers[0]["title"] == "ML Paper"
