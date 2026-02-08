"""Tests for arXiv and Semantic Scholar API clients."""

import json
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock
from io import BytesIO

from science_agent.apis import arxiv, semantic_scholar


# ── arXiv tests ──────────────────────────────────────────────────────

_ARXIV_RESPONSE = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Test Paper Title</title>
    <summary>This is the abstract.</summary>
    <published>2023-01-15T00:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/2301.00001v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""


def _mock_urlopen_arxiv(*args, **kwargs):
    resp = MagicMock()
    resp.read.return_value = _ARXIV_RESPONSE.encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_arxiv_search():
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_arxiv):
        results = arxiv.search("test query", max_results=5)
    assert len(results) == 1
    paper = results[0]
    assert paper["title"] == "Test Paper Title"
    assert paper["authors"] == ["Alice Smith", "Bob Jones"]
    assert paper["abstract"] == "This is the abstract."
    assert paper["year"] == 2023
    assert paper["arxiv_id"] == "2301.00001v1"
    assert "pdf" in paper["pdf_url"]


def test_arxiv_fetch_paper():
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_arxiv):
        paper = arxiv.fetch_paper("2301.00001")
    assert paper is not None
    assert paper["title"] == "Test Paper Title"


def test_arxiv_fetch_paper_empty():
    empty_feed = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    )
    resp = MagicMock()
    resp.read.return_value = empty_feed.encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        paper = arxiv.fetch_paper("9999.99999")
    assert paper is None


# ── Semantic Scholar tests ───────────────────────────────────────────

_S2_SEARCH_RESPONSE = {
    "data": [
        {
            "paperId": "abc123",
            "title": "S2 Test Paper",
            "authors": [{"name": "Charlie Brown"}, {"name": "Dana White"}],
            "abstract": "S2 abstract text.",
            "year": 2024,
            "externalIds": {"ArXiv": "2401.00001"},
            "url": "https://www.semanticscholar.org/paper/abc123",
            "openAccessPdf": {"url": "https://example.com/paper.pdf"},
        }
    ]
}


def _mock_urlopen_s2_search(*args, **kwargs):
    resp = MagicMock()
    resp.read.return_value = json.dumps(_S2_SEARCH_RESPONSE).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_s2_search():
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_s2_search):
        results = semantic_scholar.search("test query", limit=5)
    assert len(results) == 1
    paper = results[0]
    assert paper["title"] == "S2 Test Paper"
    assert paper["authors"] == ["Charlie Brown", "Dana White"]
    assert paper["abstract"] == "S2 abstract text."
    assert paper["year"] == 2024
    assert paper["s2_id"] == "abc123"
    assert paper["arxiv_id"] == "2401.00001"
    assert paper["pdf_url"] == "https://example.com/paper.pdf"


_S2_PAPER_RESPONSE = _S2_SEARCH_RESPONSE["data"][0]


def _mock_urlopen_s2_paper(*args, **kwargs):
    resp = MagicMock()
    resp.read.return_value = json.dumps(_S2_PAPER_RESPONSE).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def test_s2_fetch_paper():
    with patch("urllib.request.urlopen", side_effect=_mock_urlopen_s2_paper):
        paper = semantic_scholar.fetch_paper("abc123")
    assert paper is not None
    assert paper["title"] == "S2 Test Paper"
    assert paper["s2_id"] == "abc123"


def test_s2_fetch_paper_not_found():
    import urllib.error
    exc = urllib.error.HTTPError(
        url="", code=404, msg="Not Found", hdrs=None, fp=None,
    )
    with patch("urllib.request.urlopen", side_effect=exc):
        paper = semantic_scholar.fetch_paper("nonexistent")
    assert paper is None


# ── Advanced search tests ─────────────────────────────────────────


def test_arxiv_search_with_fields():
    """Verify that field-level params produce correct search_query prefixes."""
    captured_urls: list[str] = []

    def _capture_urlopen(req, **kwargs):
        captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
        return _mock_urlopen_arxiv()

    with patch("urllib.request.urlopen", side_effect=_capture_urlopen):
        arxiv.search(
            "transformers",
            author="Vaswani",
            category="cs.AI",
            max_results=5,
        )

    assert len(captured_urls) == 1
    url = captured_urls[0]
    # The search_query should contain au:, cat:, and all: joined with +AND+
    import urllib.parse
    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    sq = parsed["search_query"][0]
    assert "au:Vaswani" in sq
    assert "cat:cs.AI" in sq
    assert "all:transformers" in sq
    assert "+AND+" in sq


def test_arxiv_search_plain_fallback():
    """Plain query with no fields should use all:<query>."""
    captured_urls: list[str] = []

    def _capture_urlopen(req, **kwargs):
        captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
        return _mock_urlopen_arxiv()

    with patch("urllib.request.urlopen", side_effect=_capture_urlopen):
        arxiv.search("deep learning", max_results=3)

    url = captured_urls[0]
    import urllib.parse
    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    sq = parsed["search_query"][0]
    assert sq == "all:deep learning"
    assert "+AND+" not in sq


def test_s2_search_with_filters():
    """Verify that filter params appear as URL query params."""
    captured_urls: list[str] = []

    def _capture_urlopen(req, **kwargs):
        captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
        return _mock_urlopen_s2_search()

    with patch("urllib.request.urlopen", side_effect=_capture_urlopen):
        semantic_scholar.search(
            "attention",
            year="2020-2024",
            min_citations=50,
            open_access=True,
            fields_of_study="Computer Science",
            limit=5,
        )

    assert len(captured_urls) == 1
    url = captured_urls[0]
    import urllib.parse
    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert parsed["year"] == ["2020-2024"]
    assert parsed["minCitationCount"] == ["50"]
    assert "openAccessPdf" in parsed
    assert parsed["fieldsOfStudy"] == ["Computer Science"]


# ── Flag parsing tests ────────────────────────────────────────────

from science_agent.commands import _parse_search_flags


def test_parse_search_flags_full():
    flags = _parse_search_flags(
        "transformers --author Vaswani --year 2017-2020 --cat cs.AI "
        "--citations 50 --oa --source arxiv"
    )
    assert flags["query"] == "transformers"
    assert flags["author"] == "Vaswani"
    assert flags["year"] == "2017-2020"
    assert flags["cat"] == "cs.AI"
    assert flags["citations"] == 50
    assert flags["oa"] is True
    assert flags["source"] == "arxiv"


def test_parse_search_flags_plain():
    flags = _parse_search_flags("deep learning")
    assert flags["query"] == "deep learning"
    assert flags["author"] == ""
    assert flags["year"] == ""
    assert flags["oa"] is False
    assert flags["source"] == "both"


def test_parse_search_flags_short_aliases():
    flags = _parse_search_flags("llm --au Smith --ti reasoning --cite 10")
    assert flags["query"] == "llm"
    assert flags["author"] == "Smith"
    assert flags["title"] == "reasoning"
    assert flags["citations"] == 10
