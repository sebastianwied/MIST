"""Tests for the literature review module."""

import json
from unittest.mock import patch, MagicMock

from science_agent.review import (
    ReviewPaper,
    ReviewSession,
    extract_keywords,
    find_synonyms,
    decompose_query_mechanical,
    _parse_structured_input,
    run_searches,
    score_relevance,
    mechanical_summary,
    categorize_papers_mechanical,
    start_review,
    refine_review,
    finish_review,
    format_review_summary,
    generate_review_markdown,
)


# ── Keyword extraction ────────────────────────────────────────────

def test_extract_keywords_basic():
    kws = extract_keywords("transformer attention mechanisms")
    assert "transformer" in kws
    assert "attention" in kws
    assert "mechanisms" in kws


def test_extract_keywords_strips_question_prefix():
    kws = extract_keywords("How do transformers handle long contexts?")
    assert "transformers" in kws
    assert "long" in kws
    assert "contexts" in kws
    assert "how" not in kws
    assert "do" not in kws


def test_extract_keywords_strips_stopwords():
    kws = extract_keywords("the impact of attention on the performance")
    assert "the" not in kws
    assert "of" not in kws
    assert "on" not in kws
    assert "impact" in kws
    assert "attention" in kws
    assert "performance" in kws


# ── Synonyms ──────────────────────────────────────────────────────

def test_find_synonyms():
    syns = find_synonyms(["transformer", "attention"])
    assert any("self-attention" in s or "attention mechanism" in s for s in syns)


def test_find_synonyms_llm():
    syns = find_synonyms(["llm", "reasoning"])
    assert "large language model" in syns


def test_find_synonyms_no_match():
    syns = find_synonyms(["xyz123"])
    assert syns == []


# ── Structured input parsing ─────────────────────────────────────

def test_parse_structured_input_with_year():
    result = _parse_structured_input("transformers year:2020-2024")
    assert result["year_min"] == 2020
    assert result["year_max"] == 2024
    assert "year:" not in result["question"]
    assert "transformers" in result["question"]


def test_parse_structured_input_year_open():
    result = _parse_structured_input("attention year:2022")
    assert result["year_min"] == 2022
    assert result["year_max"] is None


def test_parse_structured_input_no_year():
    result = _parse_structured_input("deep learning survey")
    assert result["year_min"] is None
    assert result["year_max"] is None
    assert result["question"] == "deep learning survey"


# ── Query decomposition ──────────────────────────────────────────

def test_decompose_mechanical_basic():
    queries, facets = decompose_query_mechanical("transformer attention mechanisms")
    assert len(queries) >= 1
    assert len(facets) >= 1
    assert "transformer" in queries[0]


def test_decompose_mechanical_with_synonyms():
    queries, facets = decompose_query_mechanical("llm reasoning capabilities")
    # Should have an expanded query with "large language model"
    assert len(queries) >= 2
    expanded = " ".join(queries)
    assert "large language model" in expanded


# ── ReviewPaper & ReviewSession serialization ─────────────────────

def test_review_session_roundtrip():
    session = ReviewSession(
        session_id="abc123",
        original_question="test question",
        queries=["q1", "q2"],
        facets=["f1", "f2"],
        papers=[
            ReviewPaper(title="Paper A", authors=["Author 1"], year=2023),
            ReviewPaper(title="Paper B", authors=["Author 2"], year=2024),
        ],
        year_min=2020,
        year_max=2024,
        iteration=1,
    )
    json_str = session.to_json()
    restored = ReviewSession.from_json(json_str)
    assert restored.session_id == "abc123"
    assert restored.original_question == "test question"
    assert len(restored.papers) == 2
    assert restored.papers[0].title == "Paper A"
    assert restored.papers[1].year == 2024
    assert restored.year_min == 2020


# ── Scoring & summarization ──────────────────────────────────────

def test_score_relevance():
    paper = ReviewPaper(
        title="Attention Is All You Need",
        abstract="The dominant sequence transduction models are based on complex "
        "recurrent or convolutional neural networks that include an encoder "
        "and a decoder. The best performing models also connect the encoder "
        "and decoder through an attention mechanism.",
    )
    score = score_relevance(paper, ["attention", "transformer", "encoder"])
    assert 0.0 < score <= 1.0
    # "attention" and "encoder" appear, "transformer" does not
    assert score == 2 / 3


def test_score_relevance_empty_keywords():
    paper = ReviewPaper(title="Test")
    assert score_relevance(paper, []) == 0.0


def test_mechanical_summary():
    paper = ReviewPaper(abstract="This paper introduces a new method. It achieves state-of-the-art results.")
    s = mechanical_summary(paper)
    assert s == "This paper introduces a new method."


def test_mechanical_summary_long():
    paper = ReviewPaper(abstract="A" * 200 + ".")
    s = mechanical_summary(paper)
    assert len(s) <= 120


def test_mechanical_summary_empty():
    paper = ReviewPaper(abstract="")
    assert mechanical_summary(paper) == ""


def test_categorize_mechanical():
    papers = [
        ReviewPaper(title="Attention models", abstract="Self-attention mechanisms"),
        ReviewPaper(title="Graph networks", abstract="Graph neural network layers"),
    ]
    categorize_papers_mechanical(papers, ["attention", "graph"])
    assert papers[0].category == "attention"
    assert papers[1].category == "graph"


# ── Search with mocked APIs ──────────────────────────────────────

_MOCK_ARXIV = [
    {
        "title": "Paper Alpha",
        "authors": ["A1"],
        "abstract": "Abstract alpha",
        "year": 2023,
        "arxiv_id": "2301.00001",
        "source_url": "http://arxiv.org/abs/2301.00001",
        "pdf_url": "http://arxiv.org/pdf/2301.00001",
    },
]

_MOCK_S2 = [
    {
        "title": "Paper Beta",
        "authors": ["B1"],
        "abstract": "Abstract beta",
        "year": 2024,
        "s2_id": "s2beta",
        "arxiv_id": "",
        "source_url": "https://s2.org/beta",
        "pdf_url": "",
    },
]


def test_run_searches_dedup():
    """Duplicate titles across APIs should be deduplicated."""
    dup_s2 = [dict(_MOCK_ARXIV[0])]  # same title as arXiv result
    dup_s2[0]["s2_id"] = "s2dup"

    with (
        patch("science_agent.review.arxiv.search", return_value=_MOCK_ARXIV),
        patch("science_agent.review.semantic_scholar.search", return_value=dup_s2),
    ):
        papers = run_searches(["test"])
    # Should only have one paper (deduped by title)
    assert len(papers) == 1
    assert papers[0].title == "Paper Alpha"


def test_run_searches_year_filter():
    """Papers outside year range should be filtered."""
    old_paper = [dict(_MOCK_ARXIV[0])]
    old_paper[0]["year"] = 2019

    with (
        patch("science_agent.review.arxiv.search", return_value=old_paper),
        patch("science_agent.review.semantic_scholar.search", return_value=[]),
    ):
        papers = run_searches(["test"], year_min=2020, year_max=2024)
    assert len(papers) == 0


# ── Full orchestration ────────────────────────────────────────────

def test_start_review():
    with (
        patch("science_agent.review.arxiv.search", return_value=_MOCK_ARXIV),
        patch("science_agent.review.semantic_scholar.search", return_value=_MOCK_S2),
    ):
        session = start_review("transformer attention", use_llm=False)

    assert session.session_id
    assert len(session.papers) == 2
    assert session.iteration == 1
    assert len(session.queries) >= 1


def test_refine_review():
    session = ReviewSession(
        session_id="test",
        original_question="transformers",
        queries=["transformers"],
        facets=["transformers"],
        papers=[
            ReviewPaper(title="Paper Alpha", authors=["A1"], year=2023,
                        abstract="About transformers"),
        ],
        iteration=1,
    )
    new_s2 = [dict(_MOCK_S2[0])]
    with (
        patch("science_agent.review.arxiv.search", return_value=[]),
        patch("science_agent.review.semantic_scholar.search", return_value=new_s2),
    ):
        updated = refine_review(session, "long context attention", use_llm=False)

    assert updated.iteration == 2
    assert len(updated.papers) >= 2  # original + new


def test_finish_review(tmp_path):
    session = ReviewSession(
        session_id="test",
        original_question="test review question",
        queries=["q1"],
        facets=["f1"],
        papers=[
            ReviewPaper(title="Paper A", authors=["Auth"], year=2023,
                        abstract="Abstract.", category="f1",
                        summary="Summary."),
        ],
        iteration=1,
    )
    with patch("science_agent.review._DRAFTS_DIR", tmp_path):
        filename, message = finish_review(session)

    assert filename.startswith("review-")
    assert filename.endswith(".md")
    assert "1 papers" in message
    assert (tmp_path / filename).exists()
    content = (tmp_path / filename).read_text()
    assert "Paper A" in content


# ── Output formatting ────────────────────────────────────────────

def test_format_review_summary():
    session = ReviewSession(
        session_id="test",
        original_question="test question",
        queries=["q1"],
        facets=["f1"],
        papers=[
            ReviewPaper(title="Paper A", authors=["Auth"], year=2023,
                        relevance=0.8, summary="Summary A."),
        ],
        iteration=1,
    )
    text = format_review_summary(session)
    assert "test question" in text
    assert "Paper A" in text
    assert "80%" in text
    assert "done" in text.lower()


def test_generate_review_markdown():
    session = ReviewSession(
        session_id="test",
        original_question="test question",
        queries=["q1"],
        facets=["f1"],
        papers=[
            ReviewPaper(
                title="Paper A", authors=["Auth1", "Auth2"],
                year=2023, source_url="https://example.com/a",
                category="f1", summary="Summary.",
            ),
        ],
        year_min=2020,
        year_max=2024,
        iteration=1,
    )
    md = generate_review_markdown(session)
    assert "# Literature Review" in md
    assert "[Paper A](https://example.com/a)" in md
    assert "2020" in md
    assert "Auth1, Auth2" in md
