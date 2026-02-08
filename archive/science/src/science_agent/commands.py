"""Command parsing and dispatch for the science agent."""

import json
import os
import urllib.request
from pathlib import Path

from .review import start_review, format_review_summary

from mist_core.article_store import (
    add_tag,
    create_article,
    delete_article,
    get_article,
    list_articles,
    list_tags,
    set_pdf_path,
)

from .apis import arxiv, semantic_scholar

_PDF_DIR = Path("data/articles/pdfs")

_HELP_TEXT = """\
Science Agent Commands:
  search <query> [flags]    Search arXiv and Semantic Scholar
    --author <name>           Filter by author (arXiv)
    --title <text>            Filter by title (arXiv)
    --year <YYYY[-YYYY]>      Filter by year (S2)
    --cat <category>          arXiv category (e.g. cs.AI)
    --citations <n>           Min citations (S2)
    --oa                      Open access only (S2)
    --source arXiv|s2|both    Search source (default: both)
  review <question>         Start a literature review
  import <arxiv_id|doi|url> Import a paper by identifier
  articles [tag]            List saved articles
  article <id>              Show article details
  tag <article_id> <tag>    Add a tag to an article
  tags                      List all tags
  pdf <article_id>          Download PDF for an article
  help                      Show this help"""


def _format_result(paper: dict, index: int, source: str) -> str:
    """Format a single search result for display."""
    authors = ", ".join(paper.get("authors", [])[:3])
    if len(paper.get("authors", [])) > 3:
        authors += " et al."
    year = paper.get("year", "")
    year_str = f" ({year})" if year else ""
    ident = paper.get("arxiv_id") or paper.get("s2_id") or ""
    return f"  {index}. [{source}] {paper['title']}{year_str}\n     {authors}\n     ID: {ident}"


def _format_article(article: dict) -> str:
    """Format a saved article for detailed display."""
    authors = ", ".join(article.get("authors", []))
    tags = ", ".join(article.get("tags", []))
    lines = [
        f"Article #{article['id']}: {article['title']}",
        f"  Authors: {authors}",
        f"  Year: {article.get('year', 'N/A')}",
    ]
    if article.get("arxiv_id"):
        lines.append(f"  arXiv: {article['arxiv_id']}")
    if article.get("s2_id"):
        lines.append(f"  S2: {article['s2_id']}")
    if article.get("source_url"):
        lines.append(f"  URL: {article['source_url']}")
    if article.get("pdf_path"):
        lines.append(f"  PDF: {article['pdf_path']}")
    if tags:
        lines.append(f"  Tags: {tags}")
    if article.get("abstract"):
        lines.append(f"  Abstract: {article['abstract'][:300]}")
        if len(article.get("abstract", "")) > 300:
            lines[-1] += "..."
    return "\n".join(lines)


def _detect_identifier(raw: str) -> tuple[str, str]:
    """Detect the type of identifier and return (type, value).

    Returns one of: ("arxiv", id), ("doi", doi), ("s2", id), ("unknown", raw).
    """
    raw = raw.strip()
    # arXiv URL
    if "arxiv.org" in raw:
        for prefix in ("/abs/", "/pdf/"):
            if prefix in raw:
                aid = raw.split(prefix)[-1].rstrip("/").replace(".pdf", "")
                return ("arxiv", aid)
    # Explicit arXiv ID pattern (YYMM.NNNNN or category/NNNNNNN)
    if raw.replace(".", "").replace("/", "").replace("-", "").isalnum():
        parts = raw.split(".")
        if len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 4:
            return ("arxiv", raw)
    # DOI
    if raw.startswith("10.") or raw.lower().startswith("doi:"):
        doi = raw.removeprefix("doi:").removeprefix("DOI:").strip()
        return ("doi", doi)
    # S2 ID (40-char hex)
    if len(raw) == 40 and all(c in "0123456789abcdef" for c in raw.lower()):
        return ("s2", raw)
    return ("unknown", raw)


def _parse_search_flags(arg: str) -> dict:
    """Parse search flags from the command string.

    Returns a dict with keys: query, author, title, year, cat, citations,
    oa, source.  Unrecognised tokens become part of ``query``.
    """
    tokens = arg.split()
    flags: dict = {
        "query": "",
        "author": "",
        "title": "",
        "year": "",
        "cat": "",
        "citations": 0,
        "oa": False,
        "source": "both",
    }
    query_parts: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("--author", "--au") and i + 1 < len(tokens):
            flags["author"] = tokens[i + 1]
            i += 2
        elif tok in ("--title", "--ti") and i + 1 < len(tokens):
            flags["title"] = tokens[i + 1]
            i += 2
        elif tok == "--year" and i + 1 < len(tokens):
            flags["year"] = tokens[i + 1]
            i += 2
        elif tok == "--cat" and i + 1 < len(tokens):
            flags["cat"] = tokens[i + 1]
            i += 2
        elif tok in ("--citations", "--cite") and i + 1 < len(tokens):
            try:
                flags["citations"] = int(tokens[i + 1])
            except ValueError:
                pass
            i += 2
        elif tok == "--oa":
            flags["oa"] = True
            i += 1
        elif tok == "--source" and i + 1 < len(tokens):
            flags["source"] = tokens[i + 1].lower()
            i += 2
        else:
            query_parts.append(tok)
            i += 1
    flags["query"] = " ".join(query_parts)
    return flags


def handle_search(query: str) -> str:
    """Search both arXiv and Semantic Scholar."""
    if not query:
        return "Usage: search <query>"

    flags = _parse_search_flags(query)
    base_query = flags["query"]
    source = flags["source"]

    results = []
    # arXiv
    if source in ("both", "arxiv"):
        try:
            arxiv_results = arxiv.search(
                base_query,
                author=flags["author"],
                title=flags["title"],
                category=flags["cat"],
                max_results=5,
            )
            for i, paper in enumerate(arxiv_results, 1):
                results.append(_format_result(paper, i, "arXiv"))
        except Exception as exc:
            results.append(f"  arXiv error: {exc}")

    # Semantic Scholar
    if source in ("both", "s2"):
        try:
            s2_results = semantic_scholar.search(
                base_query,
                year=flags["year"],
                min_citations=flags["citations"],
                open_access=flags["oa"],
                limit=5,
            )
            offset = len(results)
            for i, paper in enumerate(s2_results, offset + 1):
                results.append(_format_result(paper, i, "S2"))
        except Exception as exc:
            results.append(f"  S2 error: {exc}")

    if not results:
        return "No results found."
    display_query = base_query or query
    return f"Search results for '{display_query}':\n" + "\n".join(results)


def handle_import(identifier: str) -> str:
    """Import a paper by arXiv ID, DOI, or URL."""
    if not identifier:
        return "Usage: import <arxiv_id|doi|url>"

    id_type, value = _detect_identifier(identifier)
    paper = None

    try:
        if id_type == "arxiv":
            paper = arxiv.fetch_paper(value)
            if paper is None:
                # Try S2 with arXiv prefix
                paper = semantic_scholar.fetch_paper(f"ARXIV:{value}")
        elif id_type == "doi":
            paper = semantic_scholar.fetch_paper(f"DOI:{value}")
        elif id_type == "s2":
            paper = semantic_scholar.fetch_paper(value)
        else:
            # Try arXiv first, then S2
            paper = arxiv.fetch_paper(value)
            if paper is None:
                paper = semantic_scholar.fetch_paper(value)
    except Exception as exc:
        return f"Error fetching paper: {exc}"

    if paper is None:
        return f"Could not find paper: {identifier}"

    article_id = create_article(
        title=paper["title"],
        authors=paper["authors"],
        abstract=paper.get("abstract"),
        year=paper.get("year"),
        source_url=paper.get("source_url"),
        arxiv_id=paper.get("arxiv_id"),
        s2_id=paper.get("s2_id"),
    )
    return f"Imported article #{article_id}: {paper['title']}"


def handle_articles(tag_filter: str) -> str:
    """List saved articles, optionally filtered by tag."""
    tag = tag_filter.strip() or None
    articles = list_articles(tag=tag)
    if not articles:
        if tag:
            return f"No articles with tag '{tag}'."
        return "No saved articles."
    lines = []
    for a in articles:
        authors_short = ", ".join(a["authors"][:2])
        if len(a["authors"]) > 2:
            authors_short += " et al."
        year = f" ({a['year']})" if a.get("year") else ""
        tags = " [" + ", ".join(a["tags"]) + "]" if a.get("tags") else ""
        lines.append(f"  #{a['id']} {a['title']}{year} — {authors_short}{tags}")
    header = f"Articles (tag: {tag}):" if tag else "Saved articles:"
    return header + "\n" + "\n".join(lines)


def handle_article(article_id_str: str) -> str:
    """Show details of a saved article."""
    if not article_id_str:
        return "Usage: article <id>"
    try:
        article_id = int(article_id_str)
    except ValueError:
        return f"Invalid article ID: {article_id_str}"
    article = get_article(article_id)
    if not article:
        return f"Article #{article_id} not found."
    return _format_article(article)


def handle_tag(arg: str) -> str:
    """Add a tag to an article."""
    parts = arg.strip().split(None, 1)
    if len(parts) < 2:
        return "Usage: tag <article_id> <tag>"
    try:
        article_id = int(parts[0])
    except ValueError:
        return f"Invalid article ID: {parts[0]}"
    tag = parts[1].strip()
    article = get_article(article_id)
    if not article:
        return f"Article #{article_id} not found."
    add_tag(article_id, tag)
    return f"Tagged article #{article_id} with '{tag}'."


def handle_tags() -> str:
    """List all tags."""
    tags = list_tags()
    if not tags:
        return "No tags yet."
    return "Tags: " + ", ".join(tags)


def handle_pdf(article_id_str: str) -> str:
    """Download PDF for an article."""
    if not article_id_str:
        return "Usage: pdf <article_id>"
    try:
        article_id = int(article_id_str)
    except ValueError:
        return f"Invalid article ID: {article_id_str}"

    article = get_article(article_id)
    if not article:
        return f"Article #{article_id} not found."

    if article.get("pdf_path") and Path(article["pdf_path"]).exists():
        return f"PDF already downloaded: {article['pdf_path']}"

    # Determine PDF URL
    pdf_url = ""
    if article.get("arxiv_id"):
        pdf_url = f"https://arxiv.org/pdf/{article['arxiv_id']}.pdf"
    # Could also try S2 openAccessPdf, but we don't store it in the DB

    if not pdf_url:
        return "No PDF URL available for this article."

    _PDF_DIR.mkdir(parents=True, exist_ok=True)
    safe_title = "".join(
        c if c.isalnum() or c in " -_" else "_"
        for c in article["title"][:60]
    ).strip()
    filename = f"{article_id}_{safe_title}.pdf"
    dest = _PDF_DIR / filename

    try:
        req = urllib.request.Request(pdf_url, headers={"User-Agent": "MIST/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())
    except Exception as exc:
        return f"Error downloading PDF: {exc}"

    set_pdf_path(article_id, str(dest))
    return f"Downloaded PDF to {dest}"


def handle_review(question: str) -> str:
    """Start a literature review session."""
    if not question:
        return "Usage: review <research question>"
    session = start_review(question, use_llm=True)
    summary = format_review_summary(session)
    # Return JSON with both session data and display text
    return json.dumps({
        "type": "review",
        "session": json.loads(session.to_json()),
        "summary": summary,
    })


def dispatch(line: str) -> str:
    """Route raw input to the appropriate handler."""
    stripped = line.strip()
    cmd, _, arg = stripped.partition(" ")
    cmd = cmd.lower()
    arg = arg.strip()

    match cmd:
        case "search":
            return handle_search(arg)
        case "review":
            return handle_review(arg)
        case "import":
            return handle_import(arg)
        case "articles":
            return handle_articles(arg)
        case "article":
            return handle_article(arg)
        case "tag":
            return handle_tag(arg)
        case "tags":
            return handle_tags()
        case "pdf":
            return handle_pdf(arg)
        case "help":
            return _HELP_TEXT
        case _:
            return f"Unknown command: {cmd}. Type 'help' for available commands."
