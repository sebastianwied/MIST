"""Topic browser widget with note listing and editing."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, ListView, ListItem, Label, RichLog, Static
from textual.worker import Worker, WorkerState

from mist_tui.messages import EditorResult
from mist_tui.widget_base import BrokerWidget


class TopicsPanel(BrokerWidget):
    """Browse topics, view synthesis, and open notes for editing."""

    DEFAULT_CSS = """
    TopicsPanel {
        height: 1fr;
        layout: vertical;
    }
    TopicsPanel #topic-list-container {
        height: 1fr;
    }
    TopicsPanel .topic-lv {
        height: 1fr;
        border: solid $primary-darken-2;
    }
    TopicsPanel RichLog {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    TopicsPanel .notes-lv {
        height: auto;
        max-height: 8;
        border: solid $primary-darken-2;
    }
    TopicsPanel .header-bar {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    TopicsPanel Button {
        min-width: 10;
        margin: 0 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._selected_slug: str = ""
        self._note_slug: str = ""
        self._note_filename: str = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Topics", classes="header-bar")
            yield ListView(
                id=f"topic-list-{self._agent_id}", classes="topic-lv",
            )
            yield RichLog(
                id=f"topic-detail-{self._agent_id}",
                highlight=True,
                markup=True,
                wrap=True,
            )
            yield Static("Notes", classes="header-bar")
            yield ListView(
                id=f"note-list-{self._agent_id}", classes="notes-lv",
            )
            yield Button("Refresh", id=f"topic-refresh-{self._agent_id}")

    def on_mount(self) -> None:
        self._load_topics()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == f"topic-refresh-{self._agent_id}":
            self._load_topics()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        list_id = event.list_view.id or ""
        if list_id == f"topic-list-{self._agent_id}":
            slug = event.item.name
            if slug:
                self._selected_slug = slug
                self.run_worker(
                    self._fetch_topic_detail(slug),
                    name="fetch_detail",
                    exclusive=True,
                )
        elif list_id == f"note-list-{self._agent_id}":
            filename = event.item.name
            if filename and self._selected_slug:
                self.run_worker(
                    self._fetch_note_content(self._selected_slug, filename),
                    name="fetch_note",
                    exclusive=True,
                )

    def _load_topics(self) -> None:
        self.run_worker(
            self._fetch_topic_index(),
            name="fetch_topics",
            exclusive=True,
        )

    # ── broker calls ──────────────────────────────────────────────

    async def _fetch_topic_index(self) -> list[dict]:
        result = await self.broker.request_service(
            "storage", "load_topic_index",
        )
        return result if isinstance(result, list) else []

    async def _fetch_topic_detail(self, slug: str) -> dict:
        """Fetch synthesis and note list for a topic."""
        synthesis = await self.broker.request_service(
            "storage", "load_topic_synthesis", {"slug": slug},
        )
        notes = await self.broker.request_service(
            "storage", "list_topic_notes", {"slug": slug},
        )
        return {
            "slug": slug,
            "synthesis": synthesis if isinstance(synthesis, str) else "",
            "notes": notes if isinstance(notes, list) else [],
        }

    async def _fetch_note_content(self, slug: str, filename: str) -> dict:
        content = await self.broker.request_service(
            "storage", "load_topic_note",
            {"slug": slug, "filename": filename},
        )
        return {
            "slug": slug,
            "filename": filename,
            "content": content if isinstance(content, str) else "",
        }

    # ── worker results ────────────────────────────────────────────

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state != WorkerState.SUCCESS:
            if event.state == WorkerState.ERROR:
                detail = self.query_one(
                    f"#topic-detail-{self._agent_id}", RichLog,
                )
                detail.write(
                    f"[bold red]Error: {event.worker.error}[/bold red]",
                )
            return

        if event.worker.name == "fetch_topics":
            topics = event.worker.result
            lv = self.query_one(f"#topic-list-{self._agent_id}", ListView)
            lv.clear()
            if not topics:
                lv.append(ListItem(Label("[dim]No topics yet[/dim]")))
                return
            for t in topics:
                slug = t.get("slug", "")
                name = t.get("name", slug)
                tid = t.get("id", "")
                item = ListItem(
                    Label(f"[{tid}] {name} ({slug})"), name=slug,
                )
                lv.append(item)
            return

        if event.worker.name == "fetch_detail":
            data = event.worker.result
            # Update synthesis
            detail = self.query_one(
                f"#topic-detail-{self._agent_id}", RichLog,
            )
            detail.clear()
            synthesis = data.get("synthesis", "")
            if synthesis:
                detail.write(synthesis)
            else:
                detail.write("[dim]No synthesis yet for this topic.[/dim]")
            # Update notes list
            notes_lv = self.query_one(
                f"#note-list-{self._agent_id}", ListView,
            )
            notes_lv.clear()
            notes = data.get("notes", [])
            if notes:
                for n in notes:
                    notes_lv.append(ListItem(Label(n), name=n))
            else:
                notes_lv.append(
                    ListItem(Label("[dim]No notes[/dim]")),
                )
            return

        if event.worker.name == "fetch_note":
            data = event.worker.result
            slug = data.get("slug", "")
            filename = data.get("filename", "")
            content = data.get("content", "")
            if not content:
                detail = self.query_one(
                    f"#topic-detail-{self._agent_id}", RichLog,
                )
                detail.write(f"[yellow]Note '{filename}' is empty.[/yellow]")
                return
            self._note_slug = slug
            self._note_filename = filename
            self.request_editor(
                content=content,
                title=f"Note: {filename}",
                on_complete=self._on_editor_dismiss,
                read_only=False,
            )
            return

        if event.worker.name == "note_save":
            detail = self.query_one(
                f"#topic-detail-{self._agent_id}", RichLog,
            )
            detail.write(
                f"[green]{event.worker.result}[/green]",
            )
            return

    # ── editor save flow ──────────────────────────────────────────

    def _on_editor_dismiss(self, result: EditorResult) -> None:
        if result.saved and self._note_slug and self._note_filename:
            self.run_worker(
                self._save_note(
                    self._note_slug, self._note_filename, result.content,
                ),
                name="note_save",
                exclusive=True,
            )

    async def _save_note(self, slug: str, filename: str, content: str) -> str:
        return await self.broker.send_command(
            self.agent_id, f"note:save {slug} {filename} {content}",
        )
