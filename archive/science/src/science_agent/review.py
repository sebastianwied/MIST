"""Literature review: query decomposition, search, scoring, and markdown output."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .apis import arxiv, semantic_scholar

# ── Stopwords for keyword extraction ──────────────────────────────

_STOPWORDS = frozenset(
    "a an and are as at be but by do for from has have how i if in into is it "
    "its me my no nor not of on or our own so than that the their them then "
    "there these they this to too up us was we were what when where which who "
    "whom why will with you your can could did does doing each few had he her "
    "here hers herself him himself his how'll i'd i'll i'm i've isn't it's "
    "let's most mustn't she she'd she'll she's should shouldn't that's "
    "there's they'd they'll they're they've wasn't weren't what's when's "
    "where's who's why's won't would wouldn't about above after again against "
    "all am any because been before being below between both during further "
    "other over same some such through under until very".split()
)

# Question prefixes to strip
_Q_PREFIXES = (
    "what is", "what are", "how do", "how does", "how can", "how to",
    "why do", "why does", "why is", "why are", "which", "where",
    "explain", "describe", "compare", "summarize", "review",
)

# Common academic synonyms for query expansion
_SYNONYMS: dict[str, list[str]] = {
    "transformer": ["attention mechanism", "self-attention"],
    "llm": ["large language model"],
    "large language model": ["llm"],
    "cnn": ["convolutional neural network"],
    "convolutional neural network": ["cnn"],
    "rnn": ["recurrent neural network"],
    "recurrent neural network": ["rnn"],
    "gan": ["generative adversarial network"],
    "generative adversarial network": ["gan"],
    "rl": ["reinforcement learning"],
    "reinforcement learning": ["rl"],
    "nlp": ["natural language processing"],
    "natural language processing": ["nlp"],
    "cv": ["computer vision"],
    "computer vision": ["cv"],
    "gnn": ["graph neural network"],
    "graph neural network": ["gnn"],
    "diffusion": ["denoising diffusion", "score-based"],
    "rag": ["retrieval augmented generation"],
    "retrieval augmented generation": ["rag"],
    "fine-tuning": ["fine tuning", "finetuning"],
    "zero-shot": ["zero shot"],
    "few-shot": ["few shot"],
}

_DRAFTS_DIR = Path("data/notes/drafts")


# ── Data structures ───────────────────────────────────────────────

@dataclass
class ReviewPaper:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    arxiv_id: str = ""
    s2_id: str = ""
    source_url: str = ""
    pdf_url: str = ""
    category: str = ""
    summary: str = ""
    relevance: float = 0.0


@dataclass
class ReviewSession:
    session_id: str = ""
    original_question: str = ""
    queries: list[str] = field(default_factory=list)
    facets: list[str] = field(default_factory=list)
    papers: list[ReviewPaper] = field(default_factory=list)
    year_min: int | None = None
    year_max: int | None = None
    iteration: int = 0

    def to_json(self) -> str:
        data = asdict(self)
        return json.dumps(data)

    @classmethod
    def from_json(cls, text: str) -> ReviewSession:
        data = json.loads(text)
        papers_raw = data.pop("papers", [])
        session = cls(**data)
        session.papers = [ReviewPaper(**p) for p in papers_raw]
        return session


# ── Keyword extraction & synonyms ────────────────────────────────

def extract_keywords(text: str) -> list[str]:
    """Strip stopwords and question prefixes, return meaningful keywords."""
    t = text.lower().strip()
    for prefix in _Q_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
            break
    # Remove punctuation except hyphens
    t = re.sub(r"[^\w\s-]", " ", t)
    words = t.split()
    keywords = [w for w in words if w not in _STOPWORDS and len(w) > 1]
    return keywords


def find_synonyms(keywords: list[str]) -> list[str]:
    """Look up synonyms for common academic terms."""
    syns: list[str] = []
    text = " ".join(keywords).lower()
    for term, alts in _SYNONYMS.items():
        if term in text:
            for alt in alts:
                if alt not in text and alt not in syns:
                    syns.append(alt)
    return syns


# ── Structured input parsing ─────────────────────────────────────

def _parse_structured_input(text: str) -> dict[str, Any]:
    """Extract year:YYYY-YYYY from input; return dict with question and years."""
    result: dict[str, Any] = {"question": text, "year_min": None, "year_max": None}
    year_match = re.search(r"year:\s*(\d{4})(?:\s*-\s*(\d{4}))?", text, re.IGNORECASE)
    if year_match:
        result["year_min"] = int(year_match.group(1))
        if year_match.group(2):
            result["year_max"] = int(year_match.group(2))
        result["question"] = text[:year_match.start()].strip() + " " + text[year_match.end():].strip()
        result["question"] = result["question"].strip()
    return result


# ── Query decomposition ──────────────────────────────────────────

def decompose_query_mechanical(
    question: str,
    year_min: int | None = None,
    year_max: int | None = None,
) -> tuple[list[str], list[str]]:
    """Build 2-3 query variants from keywords + synonyms.

    Returns (queries, facets).
    """
    keywords = extract_keywords(question)
    if not keywords:
        return ([question.strip()], [question.strip()])

    # Primary query: all keywords joined
    primary = " ".join(keywords)

    # Synonym-expanded query
    syns = find_synonyms(keywords)
    queries = [primary]
    if syns:
        expanded = primary + " " + " ".join(syns[:2])
        queries.append(expanded)

    # If enough keywords, make a narrower query from the most distinctive ones
    if len(keywords) >= 4:
        queries.append(" ".join(keywords[:3]))

    facets = list(keywords[:5])
    return queries, facets


def decompose_query_llm(
    question: str,
    year_min: int | None = None,
    year_max: int | None = None,
) -> tuple[list[str], list[str]]:
    """Use Ollama to decompose the question into facets.

    Falls back to mechanical decomposition on failure.
    """
    try:
        from mist_core.ollama_client import call_ollama
    except Exception:
        return decompose_query_mechanical(question, year_min, year_max)

    year_note = ""
    if year_min or year_max:
        year_note = f" Focus on papers from {year_min or '?'} to {year_max or 'present'}."

    prompt = (
        f"Decompose this research question into 2-3 search queries and key facets "
        f"for finding relevant academic papers.{year_note}\n\n"
        f"Question: {question}\n\n"
        f"Reply in JSON only:\n"
        f'{{"queries": ["query1", "query2"], "facets": ["facet1", "facet2", "facet3"]}}'
    )
    try:
        raw = call_ollama(prompt, command="review")
        # Extract JSON from response
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            queries = data.get("queries", [])
            facets = data.get("facets", [])
            if queries and facets:
                return queries, facets
    except Exception:
        pass
    return decompose_query_mechanical(question, year_min, year_max)


# ── Search & deduplication ────────────────────────────────────────

def run_searches(
    queries: list[str],
    *,
    max_per_query: int = 5,
    year_min: int | None = None,
    year_max: int | None = None,
) -> list[ReviewPaper]:
    """Search arXiv + S2 for each query, deduplicate, apply year filter."""
    seen_titles: set[str] = set()
    papers: list[ReviewPaper] = []

    year_range = ""
    if year_min and year_max:
        year_range = f"{year_min}-{year_max}"
    elif year_min:
        year_range = f"{year_min}-"

    for query in queries:
        # arXiv
        try:
            for p in arxiv.search(query, max_results=max_per_query):
                key = p.get("title", "").lower().strip()
                if key and key not in seen_titles:
                    seen_titles.add(key)
                    paper = _dict_to_review_paper(p)
                    if _year_ok(paper, year_min, year_max):
                        papers.append(paper)
        except Exception:
            pass

        # Semantic Scholar
        try:
            for p in semantic_scholar.search(
                query, year=year_range, limit=max_per_query,
            ):
                key = p.get("title", "").lower().strip()
                if key and key not in seen_titles:
                    seen_titles.add(key)
                    paper = _dict_to_review_paper(p)
                    if _year_ok(paper, year_min, year_max):
                        papers.append(paper)
        except Exception:
            pass

    return papers


def _dict_to_review_paper(d: dict) -> ReviewPaper:
    return ReviewPaper(
        title=d.get("title", ""),
        authors=d.get("authors", []),
        year=d.get("year"),
        abstract=d.get("abstract", ""),
        arxiv_id=d.get("arxiv_id", ""),
        s2_id=d.get("s2_id", ""),
        source_url=d.get("source_url", ""),
        pdf_url=d.get("pdf_url", ""),
    )


def _year_ok(paper: ReviewPaper, year_min: int | None, year_max: int | None) -> bool:
    if paper.year is None:
        return True
    if year_min and paper.year < year_min:
        return False
    if year_max and paper.year > year_max:
        return False
    return True


# ── Scoring & summarization ──────────────────────────────────────

def score_relevance(paper: ReviewPaper, keywords: list[str]) -> float:
    """Keyword overlap ratio (0.0–1.0)."""
    if not keywords:
        return 0.0
    text = (paper.title + " " + paper.abstract).lower()
    hits = sum(1 for kw in keywords if kw.lower() in text)
    return hits / len(keywords)


def mechanical_summary(paper: ReviewPaper) -> str:
    """First sentence of abstract, truncated to 120 chars."""
    abstract = paper.abstract.strip()
    if not abstract:
        return ""
    # First sentence
    end = abstract.find(". ")
    sentence = abstract[: end + 1] if end > 0 else abstract
    if len(sentence) > 120:
        sentence = sentence[:117] + "..."
    return sentence


def categorize_papers_mechanical(
    papers: list[ReviewPaper], facets: list[str],
) -> None:
    """Assign category based on facet keyword overlap. Mutates papers in place."""
    for paper in papers:
        text = (paper.title + " " + paper.abstract).lower()
        best_facet = ""
        best_score = 0
        for facet in facets:
            words = facet.lower().split()
            score = sum(1 for w in words if w in text)
            if score > best_score:
                best_score = score
                best_facet = facet
        paper.category = best_facet or "general"


def enhance_papers_llm(papers: list[ReviewPaper], facets: list[str]) -> None:
    """Use LLM for better summaries/categories (first 15 papers). Mutates in place."""
    try:
        from mist_core.ollama_client import call_ollama
    except Exception:
        return

    batch = papers[:15]
    if not batch:
        return

    papers_text = ""
    for i, p in enumerate(batch):
        abstract_snippet = p.abstract[:200] if p.abstract else "N/A"
        papers_text += f"{i}. {p.title}\n   Abstract: {abstract_snippet}\n\n"

    facets_str = ", ".join(facets)
    prompt = (
        f"For each paper below, provide a one-line summary and assign a category "
        f"from these facets: {facets_str}.\n\n{papers_text}"
        f"Reply in JSON only:\n"
        f'[{{"index": 0, "summary": "...", "category": "..."}}, ...]'
    )

    try:
        raw = call_ollama(prompt, command="review")
        json_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if json_match:
            items = json.loads(json_match.group())
            for item in items:
                idx = item.get("index")
                if isinstance(idx, int) and 0 <= idx < len(batch):
                    if item.get("summary"):
                        batch[idx].summary = item["summary"]
                    if item.get("category"):
                        batch[idx].category = item["category"]
    except Exception:
        pass


# ── Session orchestration ─────────────────────────────────────────

def start_review(question: str, *, use_llm: bool = True) -> ReviewSession:
    """Parse question → decompose → search → score → summarize → categorize."""
    parsed = _parse_structured_input(question)
    q = parsed["question"]
    year_min = parsed["year_min"]
    year_max = parsed["year_max"]

    if use_llm:
        queries, facets = decompose_query_llm(q, year_min, year_max)
    else:
        queries, facets = decompose_query_mechanical(q, year_min, year_max)

    papers = run_searches(
        queries, max_per_query=5, year_min=year_min, year_max=year_max,
    )

    keywords = extract_keywords(q)
    for paper in papers:
        paper.relevance = score_relevance(paper, keywords)
        if not paper.summary:
            paper.summary = mechanical_summary(paper)

    # Sort by relevance descending
    papers.sort(key=lambda p: p.relevance, reverse=True)

    if use_llm:
        enhance_papers_llm(papers, facets)
    else:
        categorize_papers_mechanical(papers, facets)

    # Fill in any remaining empty categories
    categorize_papers_mechanical(
        [p for p in papers if not p.category], facets,
    )

    session = ReviewSession(
        session_id=uuid.uuid4().hex[:12],
        original_question=question,
        queries=queries,
        facets=facets,
        papers=papers,
        year_min=year_min,
        year_max=year_max,
        iteration=1,
    )
    return session


def refine_review(
    session: ReviewSession, instruction: str, *, use_llm: bool = True,
) -> ReviewSession:
    """Adjust queries based on instruction, re-search, merge, re-score."""
    new_keywords = extract_keywords(instruction)
    if not new_keywords:
        return session

    # Build new queries by combining existing facets with new keywords
    new_query = " ".join(new_keywords)
    new_queries = [new_query]
    if session.queries:
        combined = session.queries[0] + " " + new_query
        new_queries.append(combined)

    new_papers = run_searches(
        new_queries,
        max_per_query=5,
        year_min=session.year_min,
        year_max=session.year_max,
    )

    # Merge: add papers not already present
    existing_titles = {p.title.lower().strip() for p in session.papers}
    for paper in new_papers:
        if paper.title.lower().strip() not in existing_titles:
            session.papers.append(paper)
            existing_titles.add(paper.title.lower().strip())

    # Re-score all papers with updated keywords
    all_keywords = extract_keywords(session.original_question) + new_keywords
    for paper in session.papers:
        paper.relevance = score_relevance(paper, all_keywords)
        if not paper.summary:
            paper.summary = mechanical_summary(paper)

    session.papers.sort(key=lambda p: p.relevance, reverse=True)

    # Update facets
    session.facets = list(dict.fromkeys(session.facets + new_keywords[:3]))
    session.queries = list(dict.fromkeys(session.queries + new_queries))
    session.iteration += 1

    categorize_papers_mechanical(
        [p for p in session.papers if not p.category], session.facets,
    )

    return session


def finish_review(session: ReviewSession) -> tuple[str, str]:
    """Generate markdown and save to data/notes/drafts/.

    Returns (filename, message).
    """
    md = generate_review_markdown(session)
    slug = re.sub(r"[^\w\s-]", "", session.original_question.lower())
    slug = re.sub(r"\s+", "-", slug.strip())[:40]
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"review-{slug}-{timestamp}.md"

    _DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _DRAFTS_DIR / filename
    path.write_text(md, encoding="utf-8")

    return filename, f"Review saved to drafts/{filename} ({len(session.papers)} papers)"


# ── Output formatting ────────────────────────────────────────────

def format_review_summary(session: ReviewSession) -> str:
    """Text summary for TUI display (top 10 papers, queries, facets)."""
    lines = [
        f"Literature Review: {session.original_question}",
        f"Queries: {', '.join(session.queries)}",
        f"Facets: {', '.join(session.facets)}",
        f"Papers found: {len(session.papers)}",
        "",
    ]
    for i, paper in enumerate(session.papers[:10], 1):
        authors = ", ".join(paper.authors[:2])
        if len(paper.authors) > 2:
            authors += " et al."
        year = f" ({paper.year})" if paper.year else ""
        score = f" [{paper.relevance:.0%}]"
        lines.append(f"  {i}. {paper.title}{year}{score}")
        lines.append(f"     {authors}")
        if paper.summary:
            lines.append(f"     {paper.summary}")
    if len(session.papers) > 10:
        lines.append(f"\n  ... and {len(session.papers) - 10} more papers.")
    lines.append(
        "\nRefine with additional instructions, or type 'done' to save."
    )
    return "\n".join(lines)


def generate_review_markdown(session: ReviewSession) -> str:
    """Full categorized markdown with paper links and one-line summaries."""
    lines = [
        f"# Literature Review: {session.original_question}",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d')}*",
        "",
    ]
    if session.year_min or session.year_max:
        yr = f"{session.year_min or '?'}–{session.year_max or 'present'}"
        lines.append(f"**Year range:** {yr}")
        lines.append("")

    lines.append(f"**Search queries:** {', '.join(session.queries)}")
    lines.append(f"**Facets:** {', '.join(session.facets)}")
    lines.append(f"**Total papers:** {len(session.papers)}")
    lines.append("")

    # Group by category
    categories: dict[str, list[ReviewPaper]] = {}
    for paper in session.papers:
        cat = paper.category or "general"
        categories.setdefault(cat, []).append(paper)

    for cat, cat_papers in categories.items():
        lines.append(f"## {cat.title()}")
        lines.append("")
        for paper in cat_papers:
            authors = ", ".join(paper.authors[:3])
            if len(paper.authors) > 3:
                authors += " et al."
            year = f" ({paper.year})" if paper.year else ""
            link = paper.source_url or ""
            if link:
                lines.append(f"- **[{paper.title}]({link})**{year}")
            else:
                lines.append(f"- **{paper.title}**{year}")
            lines.append(f"  {authors}")
            summary = paper.summary or mechanical_summary(paper)
            if summary:
                lines.append(f"  > {summary}")
            lines.append("")

    return "\n".join(lines)
