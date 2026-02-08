"""arXiv API client using stdlib only."""

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

_BASE_URL = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom"}


def _parse_entry(entry: ET.Element) -> dict:
    """Parse a single Atom entry into a normalized dict."""
    title_el = entry.find("atom:title", _NS)
    title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""

    authors = []
    for author in entry.findall("atom:author", _NS):
        name_el = author.find("atom:name", _NS)
        if name_el is not None and name_el.text:
            authors.append(name_el.text.strip())

    abstract_el = entry.find("atom:summary", _NS)
    abstract = (abstract_el.text or "").strip() if abstract_el is not None else ""

    published_el = entry.find("atom:published", _NS)
    year = None
    if published_el is not None and published_el.text:
        year = int(published_el.text[:4])

    # Extract arXiv ID from the entry id URL
    id_el = entry.find("atom:id", _NS)
    source_url = (id_el.text or "").strip() if id_el is not None else ""
    arxiv_id = ""
    if source_url:
        # URL format: http://arxiv.org/abs/XXXX.XXXXX[vN]
        parts = source_url.split("/abs/")
        if len(parts) == 2:
            arxiv_id = parts[1]

    # PDF link
    pdf_url = ""
    for link in entry.findall("atom:link", _NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href", "")
            break

    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "year": year,
        "arxiv_id": arxiv_id,
        "source_url": source_url,
        "pdf_url": pdf_url,
    }


def search(
    query: str = "",
    *,
    author: str = "",
    title: str = "",
    abstract: str = "",
    category: str = "",
    max_results: int = 10,
) -> list[dict]:
    """Search arXiv for papers matching *query* and/or field-level filters.

    Field prefixes (au:, ti:, abs:, cat:) are ANDed together.
    Falls back to ``all:<query>`` when only *query* is given.
    """
    parts: list[str] = []
    if author:
        parts.append(f"au:{author}")
    if title:
        parts.append(f"ti:{title}")
    if abstract:
        parts.append(f"abs:{abstract}")
    if category:
        parts.append(f"cat:{category}")
    if query:
        if parts:
            parts.append(f"all:{query}")
        else:
            parts.append(f"all:{query}")
    search_query = "+AND+".join(parts) if parts else "all:*"
    params = urllib.parse.urlencode({
        "search_query": search_query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"{_BASE_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "MIST/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    entries = root.findall("atom:entry", _NS)
    return [_parse_entry(e) for e in entries]


def fetch_paper(arxiv_id: str) -> dict | None:
    """Fetch a single paper by arXiv ID."""
    params = urllib.parse.urlencode({
        "id_list": arxiv_id,
        "max_results": 1,
    })
    url = f"{_BASE_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "MIST/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    entries = root.findall("atom:entry", _NS)
    if not entries:
        return None
    return _parse_entry(entries[0])
