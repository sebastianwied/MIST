"""Tests for science agent command dispatch with mocked broker."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from mist_client.protocol import (
    Message,
    MSG_COMMAND,
    MSG_RESPONSE,
    RESP_ERROR,
    RESP_LIST,
    RESP_TABLE,
    RESP_TEXT,
)

from science_agent.commands import (
    _detect_identifier,
    _parse_search_flags,
    dispatch,
)


class FakeBrokerClient:
    """Minimal mock of BrokerClient for testing."""

    def __init__(self):
        self.sent: list[Message] = []
        self.agent_id = "science-0"
        self._articles = []

    async def _send(self, msg):
        self.sent.append(msg)

    async def create_article(self, title, authors, **kwargs):
        self._articles.append({"id": len(self._articles) + 1, "title": title, "authors": authors, **kwargs})
        return {"article_id": len(self._articles)}

    async def list_articles(self, tag=None):
        return self._articles

    async def get_article(self, article_id):
        for a in self._articles:
            if a.get("id") == article_id:
                return a
        return None

    async def _service_request(self, service, action, params=None):
        return []

    async def respond_text(self, original, text, format="plain"):
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_TEXT, "content": {"text": text, "format": format}},
        )
        self.sent.append(reply)

    async def respond_table(self, original, columns, rows, title=""):
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_TABLE, "content": {"columns": columns, "rows": rows, "title": title}},
        )
        self.sent.append(reply)

    async def respond_list(self, original, items, title=""):
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_LIST, "content": {"items": items, "title": title}},
        )
        self.sent.append(reply)

    async def respond_error(self, original, message, code=""):
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_ERROR, "content": {"message": message, "code": code}},
        )
        self.sent.append(reply)


def _cmd(command: str, text: str = "", args: dict | None = None) -> Message:
    payload: dict = {"command": command}
    if text:
        payload["text"] = text
    if args:
        payload["args"] = args
    return Message.create(MSG_COMMAND, "ui", "science-0", payload)


@pytest.fixture
def client():
    return FakeBrokerClient()


class TestDetectIdentifier:
    def test_arxiv_url(self):
        assert _detect_identifier("https://arxiv.org/abs/2301.12345") == ("arxiv", "2301.12345")

    def test_arxiv_pdf_url(self):
        assert _detect_identifier("https://arxiv.org/pdf/2301.12345.pdf") == ("arxiv", "2301.12345")

    def test_arxiv_id(self):
        assert _detect_identifier("2301.12345") == ("arxiv", "2301.12345")

    def test_doi(self):
        assert _detect_identifier("10.1234/test")[0] == "doi"

    def test_doi_prefix(self):
        assert _detect_identifier("doi:10.1234/test") == ("doi", "10.1234/test")

    def test_s2_id(self):
        hex40 = "a" * 40
        assert _detect_identifier(hex40) == ("s2", hex40)

    def test_unknown(self):
        assert _detect_identifier("some random text")[0] == "unknown"


class TestParseSearchFlags:
    def test_basic_query(self):
        flags = _parse_search_flags("transformers attention")
        assert flags["query"] == "transformers attention"
        assert flags["source"] == "both"

    def test_author_flag(self):
        flags = _parse_search_flags("transformers --author Vaswani")
        assert flags["query"] == "transformers"
        assert flags["author"] == "Vaswani"

    def test_year_flag(self):
        flags = _parse_search_flags("--year 2020-2024 deep learning")
        assert flags["year"] == "2020-2024"

    def test_source_flag(self):
        flags = _parse_search_flags("test --source arxiv")
        assert flags["source"] == "arxiv"


class TestSearchCommand:
    async def test_search_requires_query(self, client):
        msg = _cmd("search")
        await dispatch(client, msg)
        assert client.sent[0].payload["type"] == RESP_ERROR

    async def test_search_with_mock(self, client):
        msg = _cmd("search", args={"query": "transformers"})
        mock_results = [{"title": "Attention Is All You Need", "authors": ["Vaswani"], "year": 2017, "arxiv_id": "1706.03762"}]
        with patch("science_agent.commands.arxiv.search", return_value=mock_results):
            with patch("science_agent.commands.semantic_scholar.search", return_value=[]):
                await dispatch(client, msg)
        resp = client.sent[0]
        assert resp.payload["type"] == RESP_TABLE
        assert "Attention" in str(resp.payload["content"]["rows"])


class TestImportCommand:
    async def test_import_requires_id(self, client):
        msg = _cmd("import")
        await dispatch(client, msg)
        assert client.sent[0].payload["type"] == RESP_ERROR

    async def test_import_arxiv(self, client):
        msg = _cmd("import", args={"identifier": "2301.12345"})
        mock_paper = {"title": "Test Paper", "authors": ["Author A"], "year": 2023, "arxiv_id": "2301.12345"}
        with patch("science_agent.commands.arxiv.fetch_paper", return_value=mock_paper):
            await dispatch(client, msg)
        resp = client.sent[0]
        assert resp.payload["type"] == RESP_TEXT
        assert "Imported" in resp.payload["content"]["text"]
        assert len(client._articles) == 1

    async def test_import_not_found(self, client):
        msg = _cmd("import", args={"identifier": "2301.99999"})
        with patch("science_agent.commands.arxiv.fetch_paper", return_value=None):
            with patch("science_agent.commands.semantic_scholar.fetch_paper", return_value=None):
                await dispatch(client, msg)
        resp = client.sent[0]
        assert resp.payload["type"] == RESP_ERROR


class TestArticlesCommand:
    async def test_articles_empty(self, client):
        msg = _cmd("articles")
        await dispatch(client, msg)
        assert "No saved" in client.sent[0].payload["content"]["text"]


class TestArticleCommand:
    async def test_article_not_found(self, client):
        msg = _cmd("article", args={"id": 999})
        await dispatch(client, msg)
        assert client.sent[0].payload["type"] == RESP_ERROR

    async def test_article_invalid_id(self, client):
        msg = _cmd("article", text="abc")
        await dispatch(client, msg)
        assert client.sent[0].payload["type"] == RESP_ERROR


class TestTagsCommand:
    async def test_tags_empty(self, client):
        msg = _cmd("tags")
        await dispatch(client, msg)
        assert "No tags" in client.sent[0].payload["content"]["text"]


class TestUnknownCommand:
    async def test_unknown(self, client):
        msg = _cmd("foobar")
        await dispatch(client, msg)
        assert client.sent[0].payload["type"] == RESP_ERROR
