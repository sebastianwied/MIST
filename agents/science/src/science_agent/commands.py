"""Command dispatch for the science agent."""

from __future__ import annotations

import asyncio

from mist_client import BrokerClient
from mist_client.protocol import Message

from .apis import arxiv, semantic_scholar


def _detect_identifier(raw: str) -> tuple[str, str]:
    """Detect identifier type: ("arxiv"|"doi"|"s2"|"unknown", value)."""
    raw = raw.strip()
    if "arxiv.org" in raw:
        for prefix in ("/abs/", "/pdf/"):
            if prefix in raw:
                aid = raw.split(prefix)[-1].rstrip("/").replace(".pdf", "")
                return ("arxiv", aid)
    if raw.replace(".", "").replace("/", "").replace("-", "").isalnum():
        parts = raw.split(".")
        if len(parts) == 2 and parts[0].isdigit() and len(parts[0]) == 4:
            return ("arxiv", raw)
    if raw.startswith("10.") or raw.lower().startswith("doi:"):
        doi = raw.removeprefix("doi:").removeprefix("DOI:").strip()
        return ("doi", doi)
    if len(raw) == 40 and all(c in "0123456789abcdef" for c in raw.lower()):
        return ("s2", raw)
    return ("unknown", raw)


def _parse_search_flags(arg: str) -> dict:
    """Parse search flags from command text."""
    tokens = arg.split()
    flags: dict = {
        "query": "", "author": "", "title": "", "year": "",
        "cat": "", "citations": 0, "oa": False, "source": "both",
    }
    query_parts: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("--author", "--au") and i + 1 < len(tokens):
            flags["author"] = tokens[i + 1]; i += 2
        elif tok in ("--title", "--ti") and i + 1 < len(tokens):
            flags["title"] = tokens[i + 1]; i += 2
        elif tok == "--year" and i + 1 < len(tokens):
            flags["year"] = tokens[i + 1]; i += 2
        elif tok == "--cat" and i + 1 < len(tokens):
            flags["cat"] = tokens[i + 1]; i += 2
        elif tok in ("--citations", "--cite") and i + 1 < len(tokens):
            try: flags["citations"] = int(tokens[i + 1])
            except ValueError: pass
            i += 2
        elif tok == "--oa":
            flags["oa"] = True; i += 1
        elif tok == "--source" and i + 1 < len(tokens):
            flags["source"] = tokens[i + 1].lower(); i += 2
        else:
            query_parts.append(tok); i += 1
    flags["query"] = " ".join(query_parts)
    return flags


async def dispatch(client: BrokerClient, msg: Message) -> None:
    """Route a command message to the appropriate handler."""
    payload = msg.payload
    command = payload.get("command", "")
    args = payload.get("args", {})
    text = payload.get("text", "")

    match command:
        case "search":
            query = args.get("query", "") or text
            await _handle_search(client, msg, query)
        case "import":
            identifier = args.get("identifier", "") or text
            await _handle_import(client, msg, identifier)
        case "articles":
            tag = args.get("tag", "") or text
            await _handle_articles(client, msg, tag)
        case "article":
            article_id = args.get("id") or text
            await _handle_article(client, msg, article_id)
        case "tag":
            article_id = args.get("article_id") or ""
            tag = args.get("tag", "") or ""
            if not article_id and text:
                parts = text.split(None, 1)
                article_id = parts[0] if parts else ""
                tag = parts[1] if len(parts) > 1 else ""
            await _handle_tag(client, msg, article_id, tag)
        case "tags":
            await _handle_tags(client, msg)
        case "pdf":
            article_id = args.get("article_id") or text
            await _handle_pdf(client, msg, article_id)
        case _:
            await client.respond_error(msg, f"Unknown command: {command}")


async def _handle_search(client: BrokerClient, msg: Message, query: str) -> None:
    """Search arXiv and Semantic Scholar."""
    if not query:
        await client.respond_error(msg, "Usage: search <query>")
        return

    flags = _parse_search_flags(query)
    base_query = flags["query"]
    source = flags["source"]

    results = []

    if source in ("both", "arxiv"):
        try:
            arxiv_results = await asyncio.to_thread(
                arxiv.search,
                base_query,
                author=flags["author"],
                title=flags["title"],
                category=flags["cat"],
                max_results=5,
            )
            for paper in arxiv_results:
                results.append({**paper, "_source": "arXiv"})
        except Exception as exc:
            results.append({"title": f"arXiv error: {exc}", "authors": [], "_source": "arXiv"})

    if source in ("both", "s2"):
        try:
            s2_results = await asyncio.to_thread(
                semantic_scholar.search,
                base_query,
                year=flags["year"],
                min_citations=flags["citations"],
                open_access=flags["oa"],
                limit=5,
            )
            for paper in s2_results:
                results.append({**paper, "_source": "S2"})
        except Exception as exc:
            results.append({"title": f"S2 error: {exc}", "authors": [], "_source": "S2"})

    if not results:
        await client.respond_text(msg, "No results found.")
        return

    columns = ["#", "Source", "Title", "Authors", "Year"]
    rows = []
    for i, paper in enumerate(results, 1):
        authors = ", ".join(paper.get("authors", [])[:3])
        if len(paper.get("authors", [])) > 3:
            authors += " et al."
        rows.append([
            str(i),
            paper.get("_source", ""),
            paper.get("title", ""),
            authors,
            str(paper.get("year", "")),
        ])

    await client.respond_table(msg, columns, rows, title=f"Results for '{base_query or query}'")


async def _handle_import(client: BrokerClient, msg: Message, identifier: str) -> None:
    """Import a paper by arXiv ID, DOI, or URL."""
    if not identifier:
        await client.respond_error(msg, "Usage: import <arxiv_id|doi|url>")
        return

    id_type, value = _detect_identifier(identifier)
    paper = None

    try:
        if id_type == "arxiv":
            paper = await asyncio.to_thread(arxiv.fetch_paper, value)
            if paper is None:
                paper = await asyncio.to_thread(
                    semantic_scholar.fetch_paper, f"ARXIV:{value}",
                )
        elif id_type == "doi":
            paper = await asyncio.to_thread(
                semantic_scholar.fetch_paper, f"DOI:{value}",
            )
        elif id_type == "s2":
            paper = await asyncio.to_thread(semantic_scholar.fetch_paper, value)
        else:
            paper = await asyncio.to_thread(arxiv.fetch_paper, value)
            if paper is None:
                paper = await asyncio.to_thread(semantic_scholar.fetch_paper, value)
    except Exception as exc:
        await client.respond_error(msg, f"Error fetching paper: {exc}")
        return

    if paper is None:
        await client.respond_error(msg, f"Could not find paper: {identifier}")
        return

    result = await client.create_article(
        title=paper["title"],
        authors=paper["authors"],
        abstract=paper.get("abstract"),
        year=paper.get("year"),
        source_url=paper.get("source_url"),
        arxiv_id=paper.get("arxiv_id"),
        s2_id=paper.get("s2_id"),
    )
    article_id = result.get("article_id", "?")
    await client.respond_text(msg, f"Imported article #{article_id}: {paper['title']}")


async def _handle_articles(client: BrokerClient, msg: Message, tag: str) -> None:
    """List saved articles."""
    articles = await client.list_articles(tag=tag if tag else None)
    if not articles:
        text = f"No articles with tag '{tag}'." if tag else "No saved articles."
        await client.respond_text(msg, text)
        return

    columns = ["ID", "Title", "Authors", "Year", "Tags"]
    rows = []
    for a in articles:
        authors = ", ".join(a.get("authors", [])[:2])
        if len(a.get("authors", [])) > 2:
            authors += " et al."
        tags = ", ".join(a.get("tags", []))
        rows.append([
            str(a.get("id", "")),
            a.get("title", ""),
            authors,
            str(a.get("year", "")),
            tags,
        ])
    title = f"Articles (tag: {tag})" if tag else "Saved Articles"
    await client.respond_table(msg, columns, rows, title=title)


async def _handle_article(client: BrokerClient, msg: Message, article_id) -> None:
    """Show article details."""
    if not article_id:
        await client.respond_error(msg, "Usage: article <id>")
        return
    try:
        aid = int(article_id)
    except (ValueError, TypeError):
        await client.respond_error(msg, f"Invalid article ID: {article_id}")
        return

    article = await client.get_article(aid)
    if not article:
        await client.respond_error(msg, f"Article #{aid} not found.")
        return

    lines = [
        f"**{article['title']}**",
        f"Authors: {', '.join(article.get('authors', []))}",
        f"Year: {article.get('year', 'N/A')}",
    ]
    if article.get("arxiv_id"):
        lines.append(f"arXiv: {article['arxiv_id']}")
    if article.get("s2_id"):
        lines.append(f"S2: {article['s2_id']}")
    if article.get("source_url"):
        lines.append(f"URL: {article['source_url']}")
    tags = article.get("tags", [])
    if tags:
        lines.append(f"Tags: {', '.join(tags)}")
    if article.get("abstract"):
        abstract = article["abstract"][:500]
        if len(article.get("abstract", "")) > 500:
            abstract += "..."
        lines.append(f"\n{abstract}")

    await client.respond_text(msg, "\n".join(lines), format="markdown")


async def _handle_tag(
    client: BrokerClient, msg: Message, article_id, tag: str,
) -> None:
    """Add a tag to an article."""
    if not article_id or not tag:
        await client.respond_error(msg, "Usage: tag <article_id> <tag>")
        return
    try:
        aid = int(article_id)
    except (ValueError, TypeError):
        await client.respond_error(msg, f"Invalid article ID: {article_id}")
        return

    article = await client.get_article(aid)
    if not article:
        await client.respond_error(msg, f"Article #{aid} not found.")
        return

    # Tag via service request (articles service)
    await client._service_request("articles", "add_tag", {"article_id": aid, "tag": tag})
    await client.respond_text(msg, f"Tagged article #{aid} with '{tag}'.")


async def _handle_tags(client: BrokerClient, msg: Message) -> None:
    """List all tags."""
    tags = await client._service_request("articles", "list_tags")
    if not tags:
        await client.respond_text(msg, "No tags yet.")
        return
    await client.respond_list(msg, tags, title="Tags")


async def _handle_pdf(client: BrokerClient, msg: Message, article_id) -> None:
    """Download PDF for an article."""
    if not article_id:
        await client.respond_error(msg, "Usage: pdf <article_id>")
        return
    try:
        aid = int(article_id)
    except (ValueError, TypeError):
        await client.respond_error(msg, f"Invalid article ID: {article_id}")
        return

    article = await client.get_article(aid)
    if not article:
        await client.respond_error(msg, f"Article #{aid} not found.")
        return

    if article.get("pdf_path"):
        await client.respond_text(msg, f"PDF already downloaded: {article['pdf_path']}")
        return

    pdf_url = ""
    if article.get("arxiv_id"):
        pdf_url = f"https://arxiv.org/pdf/{article['arxiv_id']}.pdf"

    if not pdf_url:
        await client.respond_error(msg, "No PDF URL available for this article.")
        return

    await client.respond_text(msg, f"PDF available at: {pdf_url}")
