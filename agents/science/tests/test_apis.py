"""Tests for API utility functions (no network calls)."""

from __future__ import annotations

from science_agent.apis.arxiv import _parse_entry
from science_agent.apis.semantic_scholar import _normalize


class TestArxivParseEntry:
    def test_basic_parsing(self):
        """Test parsing a minimal Atom entry."""
        import xml.etree.ElementTree as ET

        xml_str = """
        <entry xmlns="http://www.w3.org/2005/Atom">
            <id>http://arxiv.org/abs/2301.12345v1</id>
            <title>Test Paper Title</title>
            <summary>This is the abstract.</summary>
            <published>2023-01-30T00:00:00Z</published>
            <author><name>Alice Smith</name></author>
            <author><name>Bob Jones</name></author>
            <link title="pdf" href="http://arxiv.org/pdf/2301.12345v1"/>
        </entry>
        """
        entry = ET.fromstring(xml_str)
        result = _parse_entry(entry)
        assert result["title"] == "Test Paper Title"
        assert result["authors"] == ["Alice Smith", "Bob Jones"]
        assert result["year"] == 2023
        assert result["arxiv_id"] == "2301.12345v1"
        assert "abstract" in result


class TestS2Normalize:
    def test_basic(self):
        paper = {
            "paperId": "abc123",
            "title": "Test Paper",
            "authors": [{"name": "Alice"}, {"name": "Bob"}],
            "abstract": "An abstract.",
            "year": 2023,
            "externalIds": {"ArXiv": "2301.12345"},
            "url": "https://example.com",
            "openAccessPdf": {"url": "https://example.com/paper.pdf"},
        }
        result = _normalize(paper)
        assert result["title"] == "Test Paper"
        assert result["authors"] == ["Alice", "Bob"]
        assert result["s2_id"] == "abc123"
        assert result["arxiv_id"] == "2301.12345"
        assert result["pdf_url"] == "https://example.com/paper.pdf"

    def test_missing_fields(self):
        paper = {"paperId": "xyz", "title": "Minimal"}
        result = _normalize(paper)
        assert result["title"] == "Minimal"
        assert result["authors"] == []
        assert result["year"] is None
