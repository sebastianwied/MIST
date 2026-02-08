"""Semantic Scholar API client using stdlib only."""

import json
import urllib.request
import urllib.parse

_BASE_URL = "https://api.semanticscholar.org/graph/v1"
_FIELDS = "title,authors,abstract,year,externalIds,url,openAccessPdf"


def _normalize(paper: dict) -> dict:
    """Normalize an S2 paper response into a standard dict."""
    authors = []
    for a in paper.get("authors") or []:
        name = a.get("name", "")
        if name:
            authors.append(name)

    ext_ids = paper.get("externalIds") or {}
    arxiv_id = ext_ids.get("ArXiv", "")

    pdf_info = paper.get("openAccessPdf") or {}
    pdf_url = pdf_info.get("url", "")

    return {
        "title": (paper.get("title") or "").strip(),
        "authors": authors,
        "abstract": (paper.get("abstract") or "").strip(),
        "year": paper.get("year"),
        "s2_id": paper.get("paperId", ""),
        "arxiv_id": arxiv_id,
        "source_url": paper.get("url", ""),
        "pdf_url": pdf_url,
    }


def search(
    query: str = "",
    *,
    year: str = "",
    min_citations: int = 0,
    open_access: bool = False,
    fields_of_study: str = "",
    limit: int = 10,
) -> list[dict]:
    """Search Semantic Scholar for papers matching *query* with optional filters.

    *year*: ``"2020-2024"`` or ``"2023-"`` range string.
    *min_citations*: minimum citation count.
    *open_access*: restrict to open-access papers.
    *fields_of_study*: e.g. ``"Computer Science"``.
    """
    params: dict[str, str | int] = {
        "query": query or "",
        "limit": limit,
        "fields": _FIELDS,
    }
    if year:
        params["year"] = year
    if min_citations > 0:
        params["minCitationCount"] = min_citations
    if open_access:
        params["openAccessPdf"] = "true"
    if fields_of_study:
        params["fieldsOfStudy"] = fields_of_study
    url = f"{_BASE_URL}/paper/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "MIST/0.1"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    papers = data.get("data") or []
    return [_normalize(p) for p in papers]


def fetch_paper(paper_id: str) -> dict | None:
    """Fetch a single paper by S2 ID, DOI, or arXiv ID.

    For arXiv IDs, prefix with ``ARXIV:``.  For DOIs, prefix with ``DOI:``.
    Plain strings are treated as S2 paper IDs.
    """
    encoded = urllib.parse.quote(paper_id, safe=":")
    url = f"{_BASE_URL}/paper/{encoded}?fields={_FIELDS}"
    req = urllib.request.Request(url, headers={"User-Agent": "MIST/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    return _normalize(data)
