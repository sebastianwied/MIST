"""Science library panel: article search and browsing."""

from __future__ import annotations

import json
from enum import Enum, auto

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, Checkbox, Input, Label, ListView, ListItem,
    RichLog, Select, Static,
)
from textual.worker import Worker, WorkerState

from mist_tui.widget_base import BrokerWidget


class _Mode(Enum):
    LIBRARY = auto()
    SEARCH = auto()
    REVIEW = auto()


class _AdvancedForm(Static):
    """Collapsible advanced search form."""

    DEFAULT_CSS = """
    _AdvancedForm {
        height: auto;
        padding: 0 1;
        border: solid $primary-darken-3;
        display: none;
    }
    _AdvancedForm.visible {
        display: block;
    }
    _AdvancedForm .adv-row {
        height: auto;
        max-height: 3;
    }
    _AdvancedForm Input {
        width: 1fr;
        dock: none;
    }
    _AdvancedForm Label {
        width: auto;
        min-width: 12;
        padding: 0 1 0 0;
    }
    _AdvancedForm Button {
        min-width: 10;
        margin: 0 1;
    }
    """

    def __init__(self, form_id: str) -> None:
        super().__init__(id=form_id)
        self._fid = form_id

    def compose(self) -> ComposeResult:
        fid = self._fid
        with Horizontal(classes="adv-row"):
            yield Label("Author:")
            yield Input(placeholder="e.g. Vaswani", id=f"{fid}-author")
            yield Label("Title:")
            yield Input(placeholder="e.g. attention", id=f"{fid}-title")
        with Horizontal(classes="adv-row"):
            yield Label("Year from:")
            yield Input(placeholder="e.g. 2020", id=f"{fid}-year-from")
            yield Label("to:")
            yield Input(placeholder="e.g. 2024", id=f"{fid}-year-to")
            yield Label("Category:")
            yield Input(placeholder="e.g. cs.AI", id=f"{fid}-cat")
        with Horizontal(classes="adv-row"):
            yield Label("Min cites:")
            yield Input(placeholder="e.g. 50", id=f"{fid}-cites")
            yield Checkbox("Open Access", id=f"{fid}-oa")
            yield Label("Source:")
            yield Select(
                [("Both", "both"), ("arXiv", "arxiv"), ("Semantic Scholar", "s2")],
                value="both",
                id=f"{fid}-source",
                allow_blank=False,
            )
        with Horizontal(classes="adv-row"):
            yield Button("Search", id=f"{fid}-submit", variant="primary")
            yield Button("Clear", id=f"{fid}-clear")

    def collect_flags(self) -> str:
        """Collect non-empty fields and build a flag string."""
        fid = self._fid
        parts: list[str] = []
        author = self.query_one(f"#{fid}-author", Input).value.strip()
        title = self.query_one(f"#{fid}-title", Input).value.strip()
        year_from = self.query_one(f"#{fid}-year-from", Input).value.strip()
        year_to = self.query_one(f"#{fid}-year-to", Input).value.strip()
        cat = self.query_one(f"#{fid}-cat", Input).value.strip()
        cites = self.query_one(f"#{fid}-cites", Input).value.strip()
        oa = self.query_one(f"#{fid}-oa", Checkbox).value
        source = self.query_one(f"#{fid}-source", Select).value

        if author:
            parts.append(f"--author {author}")
        if title:
            parts.append(f"--title {title}")
        if year_from and year_to:
            parts.append(f"--year {year_from}-{year_to}")
        elif year_from:
            parts.append(f"--year {year_from}")
        if cat:
            parts.append(f"--cat {cat}")
        if cites:
            parts.append(f"--citations {cites}")
        if oa:
            parts.append("--oa")
        if source and source != "both":
            parts.append(f"--source {source}")
        return " ".join(parts)

    def clear_fields(self) -> None:
        fid = self._fid
        for suffix in ("author", "title", "year-from", "year-to", "cat", "cites"):
            self.query_one(f"#{fid}-{suffix}", Input).value = ""
        self.query_one(f"#{fid}-oa", Checkbox).value = False
        self.query_one(f"#{fid}-source", Select).value = "both"


class ScienceLibraryPanel(BrokerWidget):
    """Article search and library browser panel."""

    DEFAULT_CSS = """
    ScienceLibraryPanel {
        height: 1fr;
        layout: vertical;
    }
    ScienceLibraryPanel #sci-main {
        height: 1fr;
    }
    ScienceLibraryPanel .article-list {
        width: 40%;
        height: 1fr;
        border: solid $primary-darken-2;
    }
    ScienceLibraryPanel .detail-view {
        width: 60%;
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    ScienceLibraryPanel .toolbar {
        height: auto;
        max-height: 3;
        padding: 0 1;
    }
    ScienceLibraryPanel .toolbar Button {
        min-width: 10;
        margin: 0 1;
    }
    ScienceLibraryPanel .status-bar {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    ScienceLibraryPanel #sci-input-wrap Input {
        dock: bottom;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._mode = _Mode.LIBRARY
        self._search_results: list[dict] = []
        self._library_articles: list[dict] = []
        self._selected_index: int = -1
        self._selected_article: dict | None = None
        self._review_session: dict | None = None
        self._adv_visible: bool = False

    def compose(self) -> ComposeResult:
        aid = self._agent_id
        with Vertical():
            with Horizontal(id="sci-main"):
                yield ListView(id=f"sci-list-{aid}", classes="article-list")
                yield RichLog(
                    id=f"sci-detail-{aid}",
                    highlight=True,
                    markup=True,
                    wrap=True,
                    classes="detail-view",
                )
            with Horizontal(classes="toolbar"):
                yield Button(
                    "Library", id=f"sci-mode-lib-{aid}", variant="primary",
                )
                yield Button("Search", id=f"sci-mode-search-{aid}")
                yield Button("Advanced", id=f"sci-adv-toggle-{aid}")
                yield Button("Save", id=f"sci-save-{aid}")
                yield Button("PDF", id=f"sci-pdf-{aid}")
                yield Button("Tag", id=f"sci-tag-{aid}")
                yield Button("Refresh", id=f"sci-refresh-{aid}")
            yield _AdvancedForm(f"sci-adv-{aid}")
            yield Static(
                "", id=f"sci-status-{aid}", classes="status-bar",
            )
            yield Input(
                placeholder="Search papers...",
                id=f"sci-input-{aid}",
            )

    def on_mount(self) -> None:
        self._load_library()

    # ── mode switching ────────────────────────────────────────────

    def _set_mode(self, mode: _Mode) -> None:
        self._mode = mode
        aid = self._agent_id
        lib_btn = self.query_one(f"#sci-mode-lib-{aid}", Button)
        search_btn = self.query_one(f"#sci-mode-search-{aid}", Button)
        inp = self.query_one(f"#sci-input-{aid}", Input)
        if mode == _Mode.LIBRARY:
            lib_btn.variant = "primary"
            search_btn.variant = "default"
            inp.placeholder = "Filter by tag..."
            self._review_session = None
            self._load_library()
        elif mode == _Mode.SEARCH:
            lib_btn.variant = "default"
            search_btn.variant = "primary"
            inp.placeholder = "Search papers..."
            self._review_session = None
        elif mode == _Mode.REVIEW:
            lib_btn.variant = "default"
            search_btn.variant = "default"
            inp.placeholder = "Refine review or type 'done' to save..."

    # ── advanced form toggle ──────────────────────────────────────

    def _toggle_advanced(self) -> None:
        aid = self._agent_id
        form = self.query_one(f"#sci-adv-{aid}", _AdvancedForm)
        self._adv_visible = not self._adv_visible
        if self._adv_visible:
            form.add_class("visible")
            # Switch to search mode when opening advanced form
            if self._mode != _Mode.SEARCH:
                self._set_mode(_Mode.SEARCH)
        else:
            form.remove_class("visible")

    def _on_advanced_search(self) -> None:
        """Collect advanced form fields and run the search."""
        aid = self._agent_id
        form = self.query_one(f"#sci-adv-{aid}", _AdvancedForm)
        flags = form.collect_flags()

        # Get the main query from the input field
        inp = self.query_one(f"#sci-input-{aid}", Input)
        query = inp.value.strip()

        cmd = query
        if flags:
            cmd = f"{query} {flags}".strip()

        if not cmd:
            self._set_status("Enter a query or fill in at least one field.")
            return

        inp.clear()
        self._set_mode(_Mode.SEARCH)
        self._set_status("Searching...")
        self.run_worker(
            self._cmd_search(cmd), name="search", exclusive=True,
        )

    def _on_advanced_clear(self) -> None:
        aid = self._agent_id
        form = self.query_one(f"#sci-adv-{aid}", _AdvancedForm)
        form.clear_fields()

    # ── button handlers ───────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        aid = self._agent_id
        btn_id = event.button.id or ""
        if btn_id == f"sci-mode-lib-{aid}":
            self._set_mode(_Mode.LIBRARY)
        elif btn_id == f"sci-mode-search-{aid}":
            self._set_mode(_Mode.SEARCH)
        elif btn_id == f"sci-adv-toggle-{aid}":
            self._toggle_advanced()
        elif btn_id == f"sci-adv-{aid}-submit":
            self._on_advanced_search()
        elif btn_id == f"sci-adv-{aid}-clear":
            self._on_advanced_clear()
        elif btn_id == f"sci-save-{aid}":
            self._on_save()
        elif btn_id == f"sci-pdf-{aid}":
            self._on_pdf()
        elif btn_id == f"sci-tag-{aid}":
            self._on_tag()
        elif btn_id == f"sci-refresh-{aid}":
            if self._mode == _Mode.LIBRARY:
                self._load_library()

    # ── list selection ────────────────────────────────────────────

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        idx_str = event.item.name
        if idx_str is None:
            return
        try:
            idx = int(idx_str)
        except ValueError:
            return
        self._selected_index = idx
        if self._mode == _Mode.SEARCH:
            if 0 <= idx < len(self._search_results):
                self._show_search_detail(self._search_results[idx])
        elif self._mode == _Mode.LIBRARY:
            if 0 <= idx < len(self._library_articles):
                article = self._library_articles[idx]
                self._selected_article = article
                self._show_article_detail(article)

    # ── actions ───────────────────────────────────────────────────

    def _on_save(self) -> None:
        """Save the selected search result to the library."""
        if self._mode != _Mode.SEARCH:
            self._set_status("Switch to Search mode to save results.")
            return
        if self._selected_index < 0 or self._selected_index >= len(self._search_results):
            self._set_status("Select a search result first.")
            return
        paper = self._search_results[self._selected_index]
        self._set_status("Saving...")
        self.run_worker(
            self._cmd_save(paper), name="save", exclusive=True,
        )

    def _on_pdf(self) -> None:
        """Download PDF for the selected article."""
        if self._mode != _Mode.LIBRARY or not self._selected_article:
            self._set_status("Select a library article first.")
            return
        article_id = self._selected_article.get("id")
        if not article_id:
            return
        self._set_status("Downloading PDF...")
        self.run_worker(
            self._cmd_pdf(article_id), name="pdf", exclusive=True,
        )

    def _on_tag(self) -> None:
        """Prompt for a tag via the input field."""
        if self._mode != _Mode.LIBRARY or not self._selected_article:
            self._set_status("Select a library article first.")
            return
        aid = self._agent_id
        inp = self.query_one(f"#sci-input-{aid}", Input)
        inp.placeholder = f"Enter tag for article #{self._selected_article.get('id', '')}..."
        inp.focus()
        self._tag_pending = True

    _tag_pending: bool = False

    def _handle_tag_input(self, text: str) -> bool:
        """If a tag is pending, process it. Returns True if handled."""
        if not self._tag_pending:
            return False
        self._tag_pending = False
        aid = self._agent_id
        inp = self.query_one(f"#sci-input-{aid}", Input)
        inp.placeholder = "Filter by tag..."
        if not self._selected_article:
            return True
        article_id = self._selected_article.get("id")
        if not article_id:
            return True
        self._set_status(f"Tagging #{article_id} with '{text}'...")
        self.run_worker(
            self._cmd_tag(article_id, text), name="tag", exclusive=True,
        )
        return True

    # ── input ─────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Ignore submissions from advanced form inputs
        aid = self._agent_id
        if event.input.id and event.input.id.startswith(f"sci-adv-{aid}-"):
            return

        text = event.value.strip()
        if not text:
            if self._mode == _Mode.LIBRARY:
                self._load_library()
            return
        event.input.clear()

        if self._handle_tag_input(text):
            return

        # Review mode handling
        if self._mode == _Mode.REVIEW:
            if text.lower() == "done":
                self._review_done()
            else:
                self._review_refine(text)
            return

        if self._mode == _Mode.SEARCH:
            # Detect review prefix
            if text.lower().startswith("review "):
                self._set_status("Starting literature review...")
                self.run_worker(
                    self._cmd_review(text[7:]), name="review_start",
                    exclusive=True,
                )
                return
            self._set_status("Searching...")
            self.run_worker(
                self._cmd_search(text), name="search", exclusive=True,
            )
        else:
            self._set_status(f"Filtering by tag: {text}")
            self.run_worker(
                self._fetch_articles(tag=text), name="fetch_lib", exclusive=True,
            )

    # ── review flow ───────────────────────────────────────────────

    def _review_refine(self, instruction: str) -> None:
        if not self._review_session:
            self._set_status("No active review session.")
            return
        self._set_status("Refining review...")
        payload = json.dumps({
            "session": self._review_session,
            "instruction": instruction,
        })
        self.run_worker(
            self.broker.send_command(
                self.agent_id, f"review:refine {payload}", timeout=60.0,
            ),
            name="review_refine",
            exclusive=True,
        )

    def _review_done(self) -> None:
        if not self._review_session:
            self._set_status("No active review session.")
            return
        self._set_status("Saving review to drafts...")
        payload = json.dumps({"session": self._review_session})
        self.run_worker(
            self.broker.send_command(
                self.agent_id, f"review:done {payload}", timeout=30.0,
            ),
            name="review_done",
            exclusive=True,
        )

    # ── display helpers ───────────────────────────────────────────

    def _set_status(self, msg: str) -> None:
        self.query_one(f"#sci-status-{self._agent_id}", Static).update(
            f"  {msg}",
        )

    def _clear_status(self) -> None:
        self.query_one(f"#sci-status-{self._agent_id}", Static).update("")

    def _show_search_detail(self, paper: dict) -> None:
        detail = self.query_one(f"#sci-detail-{self._agent_id}", RichLog)
        detail.clear()
        authors = ", ".join(paper.get("authors", []))
        year = paper.get("year", "N/A")
        detail.write(f"[bold]{paper.get('title', '')}[/bold]")
        detail.write(f"Authors: {authors}")
        detail.write(f"Year: {year}")
        if paper.get("arxiv_id"):
            detail.write(f"arXiv: {paper['arxiv_id']}")
        if paper.get("s2_id"):
            detail.write(f"S2: {paper['s2_id']}")
        if paper.get("source_url"):
            detail.write(f"URL: {paper['source_url']}")
        abstract = paper.get("abstract", "")
        if abstract:
            detail.write("")
            detail.write(abstract)

    def _show_article_detail(self, article: dict) -> None:
        detail = self.query_one(f"#sci-detail-{self._agent_id}", RichLog)
        detail.clear()
        authors = ", ".join(article.get("authors", []))
        year = article.get("year", "N/A")
        tags = article.get("tags", [])
        detail.write(f"[bold]#{article.get('id', '')} {article.get('title', '')}[/bold]")
        detail.write(f"Authors: {authors}")
        detail.write(f"Year: {year}")
        if article.get("arxiv_id"):
            detail.write(f"arXiv: {article['arxiv_id']}")
        if article.get("s2_id"):
            detail.write(f"S2: {article['s2_id']}")
        if article.get("source_url"):
            detail.write(f"URL: {article['source_url']}")
        if article.get("pdf_path"):
            detail.write(f"PDF: {article['pdf_path']}")
        if tags:
            detail.write(f"Tags: {', '.join(tags)}")
        abstract = article.get("abstract", "")
        if abstract:
            detail.write("")
            detail.write(abstract)

    def _show_review_summary(self, summary: str) -> None:
        detail = self.query_one(f"#sci-detail-{self._agent_id}", RichLog)
        detail.clear()
        for line in summary.split("\n"):
            detail.write(line)

    def _populate_list(self, items: list[dict], mode: str) -> None:
        lv = self.query_one(f"#sci-list-{self._agent_id}", ListView)
        lv.clear()
        if not items:
            lv.append(ListItem(Label("[dim]No articles[/dim]")))
            return
        for i, item in enumerate(items):
            title = item.get("title", "Untitled")
            year = item.get("year", "")
            year_str = f" ({year})" if year else ""
            if mode == "library":
                prefix = f"#{item.get('id', '')} "
            else:
                source = "arXiv" if item.get("arxiv_id") else "S2"
                prefix = f"[{source}] "
            label = f"{prefix}{title[:60]}{year_str}"
            lv.append(ListItem(Label(label), name=str(i)))

    # ── data loading ──────────────────────────────────────────────

    def _load_library(self) -> None:
        self.run_worker(
            self._fetch_articles(), name="fetch_lib", exclusive=True,
        )

    # ── broker calls ──────────────────────────────────────────────

    async def _fetch_articles(self, tag: str | None = None) -> list[dict]:
        params = {"tag": tag} if tag else {}
        result = await self.broker.request_service(
            "articles", "list", params,
        )
        return result if isinstance(result, list) else []

    async def _cmd_search(self, query: str) -> str:
        return await self.broker.send_command(
            self.agent_id, f"search {query}", timeout=30.0,
        )

    async def _cmd_review(self, question: str) -> str:
        return await self.broker.send_command(
            self.agent_id, f"review {question}", timeout=60.0,
        )

    async def _cmd_save(self, paper: dict) -> str:
        payload = json.dumps(paper)
        return await self.broker.send_command(
            self.agent_id, f"article:save {payload}",
        )

    async def _cmd_pdf(self, article_id: int) -> str:
        return await self.broker.send_command(
            self.agent_id, f"article:pdf {article_id}",
        )

    async def _cmd_tag(self, article_id: int, tag: str) -> str:
        return await self.broker.send_command(
            self.agent_id, f"article:tag {article_id} {tag}",
        )

    # ── worker results ────────────────────────────────────────────

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.ERROR:
            self._set_status(f"Error: {event.worker.error}")
            return
        if event.state != WorkerState.SUCCESS:
            return

        result = event.worker.result
        name = event.worker.name

        if name == "fetch_lib":
            self._library_articles = result
            self._selected_index = -1
            self._selected_article = None
            self._populate_list(result, "library")
            self._clear_status()
            return

        if name == "search":
            self._clear_status()
            # Parse search results text to extract structured data
            # The search command returns formatted text, but we also
            # need the raw data for the save flow. We'll re-search
            # via the API client in a background thread.
            self.run_worker(
                self._fetch_search_results(result),
                name="parse_search",
                exclusive=True,
            )
            return

        if name == "parse_search":
            self._search_results = result
            self._selected_index = -1
            self._populate_list(result, "search")
            self._clear_status()
            return

        if name == "save":
            self._clear_status()
            try:
                data = json.loads(result)
                self._set_status(
                    f"Saved article #{data.get('article_id', '')}: "
                    f"{data.get('title', '')}",
                )
            except (json.JSONDecodeError, TypeError):
                self._set_status(result)
            return

        if name == "pdf":
            self._set_status(result)
            if self._mode == _Mode.LIBRARY:
                self._load_library()
            return

        if name == "tag":
            self._set_status(result)
            if self._mode == _Mode.LIBRARY:
                self._load_library()
            return

        if name in ("review_start", "review_refine"):
            self._clear_status()
            try:
                data = json.loads(result)
                if data.get("type") == "review":
                    self._review_session = data.get("session")
                    self._set_mode(_Mode.REVIEW)
                    self._show_review_summary(data.get("summary", ""))
                else:
                    self._set_status(result)
            except (json.JSONDecodeError, TypeError):
                self._set_status(result)
            return

        if name == "review_done":
            self._clear_status()
            try:
                data = json.loads(result)
                self._set_status(data.get("message", "Review saved."))
            except (json.JSONDecodeError, TypeError):
                self._set_status(result)
            self._review_session = None
            self._set_mode(_Mode.SEARCH)
            return

    async def _fetch_search_results(self, raw_text: str) -> list[dict]:
        """Re-fetch search results to get structured data.

        The search command returns formatted text. To get structured data
        for saving, we extract the query and search again directly via
        the API modules.
        """
        # Extract query from the response header "Search results for 'QUERY':"
        query = ""
        if raw_text.startswith("Search results for '"):
            end = raw_text.index("'", 20)
            query = raw_text[20:end]

        if not query:
            return []

        import asyncio
        from ..apis import arxiv, semantic_scholar

        results = []
        try:
            arxiv_results = await asyncio.to_thread(arxiv.search, query, max_results=5)
            results.extend(arxiv_results)
        except Exception:
            pass
        try:
            s2_results = await asyncio.to_thread(semantic_scholar.search, query, limit=5)
            results.extend(s2_results)
        except Exception:
            pass
        return results
