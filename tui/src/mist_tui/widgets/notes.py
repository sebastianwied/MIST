"""Topic-aware note browser panel."""

from __future__ import annotations

import logging
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    ListItem,
    ListView,
    Markdown,
    Static,
)
from textual.worker import Worker, WorkerState

from ..messages import EditorResult, RequestFullScreenEditor
from ..widget_base import BrokerWidget

log = logging.getLogger(__name__)


class NoteBrowserPanel(BrokerWidget):
    """Note browser with topic sidebar, note list, and markdown viewer.

    Broker service actions used (not yet implemented on broker side):
    - ``storage.list_topics`` -> list of topic dicts
    - ``storage.list_notes`` -> list of note dicts for a topic
    - ``storage.read_note`` -> note content string
    - ``storage.write_note`` -> write/overwrite a note
    - ``storage.delete_note`` -> delete a note
    """

    DEFAULT_CSS = """
    NoteBrowserPanel {
        height: 1fr;
        layout: horizontal;
    }
    NoteBrowserPanel #notes-sidebar {
        width: 28;
        layout: vertical;
        border-right: solid $primary-darken-2;
    }
    NoteBrowserPanel #topic-list-label,
    NoteBrowserPanel #note-list-label {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    NoteBrowserPanel #topic-list {
        height: 1fr;
        max-height: 50%;
    }
    NoteBrowserPanel #note-list {
        height: 1fr;
    }
    NoteBrowserPanel #notes-content {
        width: 1fr;
        layout: vertical;
    }
    NoteBrowserPanel #note-viewer {
        height: 1fr;
        padding: 0 1;
    }
    NoteBrowserPanel #notes-actions {
        height: 3;
        padding: 0 1;
        align: left middle;
    }
    NoteBrowserPanel #notes-actions Button {
        margin: 0 1 0 0;
    }
    NoteBrowserPanel #notes-status {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+n", "new_note", "New", show=True),
        Binding("ctrl+r", "refresh", "Refresh", show=True),
    ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._topics: list[dict[str, Any]] = []
        self._notes: list[dict[str, Any]] = []
        self._selected_topic: dict[str, Any] | None = None
        self._selected_note: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="notes-sidebar"):
                yield Static("Topics", id="topic-list-label")
                yield ListView(id="topic-list")
                yield Static("Notes", id="note-list-label")
                yield ListView(id="note-list")
            with Vertical(id="notes-content"):
                yield Markdown("*Select a topic and note to view.*", id="note-viewer")
                with Horizontal(id="notes-actions"):
                    yield Button("New", id="btn-new", variant="primary")
                    yield Button("Edit", id="btn-edit")
                    yield Button("Full Edit", id="btn-full-edit")
                    yield Button("Delete", id="btn-delete", variant="error")
                    yield Button("Refresh", id="btn-refresh")
                yield Static("", id="notes-status")

    def on_mount(self) -> None:
        self.run_worker(self._load_topics(), exclusive=True, name="_load_topics")

    async def _load_topics(self) -> list[dict[str, Any]]:
        result = await self.broker.request_service(
            "storage", "list_topics", {},
        )
        return result if isinstance(result, list) else []

    async def _load_notes(self, topic_slug: str) -> list[dict[str, Any]]:
        result = await self.broker.request_service(
            "storage", "list_notes", {"topic_slug": topic_slug},
        )
        return result if isinstance(result, list) else []

    async def _load_note_content(self, topic_slug: str, note_id: str) -> str:
        result = await self.broker.request_service(
            "storage", "read_note",
            {"topic_slug": topic_slug, "note_id": note_id},
        )
        return result if isinstance(result, str) else ""

    async def _save_note(
        self, topic_slug: str, note_id: str | None, content: str,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "topic_slug": topic_slug,
            "content": content,
        }
        if note_id is not None:
            params["note_id"] = note_id
        result = await self.broker.request_service(
            "storage", "write_note", params,
        )
        return result if isinstance(result, dict) else {}

    async def _delete_note(self, topic_slug: str, note_id: str) -> None:
        await self.broker.request_service(
            "storage", "delete_note",
            {"topic_slug": topic_slug, "note_id": note_id},
        )

    # --- Worker result handling ---

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        status = self.query_one("#notes-status", Static)

        if event.worker.name == "_load_topics":
            if event.state == WorkerState.SUCCESS:
                self._topics = event.worker.result
                self._populate_topic_list()
                status.update(f"{len(self._topics)} topic(s)")
            elif event.state == WorkerState.ERROR:
                status.update(f"Error loading topics: {event.worker.error}")

        elif event.worker.name == "_load_notes":
            if event.state == WorkerState.SUCCESS:
                self._notes = event.worker.result
                self._populate_note_list()
                status.update(f"{len(self._notes)} note(s)")
            elif event.state == WorkerState.ERROR:
                status.update(f"Error loading notes: {event.worker.error}")

        elif event.worker.name == "_load_note_content":
            if event.state == WorkerState.SUCCESS:
                viewer = self.query_one("#note-viewer", Markdown)
                viewer.update(event.worker.result)
            elif event.state == WorkerState.ERROR:
                status.update(f"Error loading note: {event.worker.error}")

    # --- UI population ---

    def _populate_topic_list(self) -> None:
        topic_list = self.query_one("#topic-list", ListView)
        topic_list.clear()
        for topic in self._topics:
            name = topic.get("name", topic.get("slug", "?"))
            topic_list.append(ListItem(Static(name)))

    def _populate_note_list(self) -> None:
        note_list = self.query_one("#note-list", ListView)
        note_list.clear()
        for note in self._notes:
            label = note.get("title", note.get("id", "untitled"))
            note_list.append(ListItem(Static(label)))

    # --- List selection ---

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        list_view = event.list_view

        if list_view.id == "topic-list":
            idx = event.list_view.index
            if idx is not None and 0 <= idx < len(self._topics):
                self._selected_topic = self._topics[idx]
                self._selected_note = None
                slug = self._selected_topic.get("slug", "")
                self.run_worker(
                    self._load_notes(slug),
                    exclusive=True,
                    name="_load_notes",
                )

        elif list_view.id == "note-list":
            idx = event.list_view.index
            if (
                idx is not None
                and 0 <= idx < len(self._notes)
                and self._selected_topic is not None
            ):
                self._selected_note = self._notes[idx]
                slug = self._selected_topic.get("slug", "")
                note_id = self._selected_note.get("id", "")
                self.run_worker(
                    self._load_note_content(slug, note_id),
                    exclusive=True,
                    name="_load_note_content",
                )

    # --- Button handlers ---

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-new":
            self._action_new_note()
        elif event.button.id == "btn-edit":
            self._action_edit_note(full_screen=False)
        elif event.button.id == "btn-full-edit":
            self._action_edit_note(full_screen=True)
        elif event.button.id == "btn-delete":
            self._action_delete_note()
        elif event.button.id == "btn-refresh":
            self.action_refresh()

    def action_new_note(self) -> None:
        self._action_new_note()

    def _action_new_note(self) -> None:
        if self._selected_topic is None:
            status = self.query_one("#notes-status", Static)
            status.update("Select a topic first")
            return

        slug = self._selected_topic.get("slug", "")
        self.post_message(
            RequestFullScreenEditor(
                content="",
                title=f"New note in {self._selected_topic.get('name', slug)}",
                on_complete=lambda result: self._on_new_note_complete(slug, result),
                metadata={"topic_slug": slug, "action": "new"},
            )
        )

    def _on_new_note_complete(self, topic_slug: str, result: EditorResult) -> None:
        if result.saved and result.content.strip():
            self.run_worker(
                self._save_note(topic_slug, None, result.content),
                exclusive=True,
                name="_save_note",
            )
            self.run_worker(
                self._load_notes(topic_slug),
                exclusive=False,
                name="_load_notes",
            )

    def _action_edit_note(self, full_screen: bool = False) -> None:
        if self._selected_topic is None or self._selected_note is None:
            status = self.query_one("#notes-status", Static)
            status.update("Select a note first")
            return

        slug = self._selected_topic.get("slug", "")
        note_id = self._selected_note.get("id", "")
        viewer = self.query_one("#note-viewer", Markdown)

        # For full-screen, post the message to open the editor screen
        if full_screen:
            self.post_message(
                RequestFullScreenEditor(
                    content=viewer._markdown,
                    title=f"Edit: {self._selected_note.get('title', note_id)}",
                    on_complete=lambda result: self._on_edit_complete(
                        slug, note_id, result,
                    ),
                    metadata={
                        "topic_slug": slug,
                        "note_id": note_id,
                        "action": "edit",
                    },
                )
            )

    def _on_edit_complete(
        self, topic_slug: str, note_id: str, result: EditorResult,
    ) -> None:
        if result.saved and result.content.strip():
            self.run_worker(
                self._save_note(topic_slug, note_id, result.content),
                exclusive=True,
                name="_save_note",
            )
            self.run_worker(
                self._load_notes(topic_slug),
                exclusive=False,
                name="_load_notes",
            )

    def _action_delete_note(self) -> None:
        if self._selected_topic is None or self._selected_note is None:
            status = self.query_one("#notes-status", Static)
            status.update("Select a note first")
            return

        slug = self._selected_topic.get("slug", "")
        note_id = self._selected_note.get("id", "")
        self._selected_note = None
        self.run_worker(
            self._delete_note(slug, note_id),
            exclusive=True,
            name="_delete_note",
        )
        # Refresh note list
        self.run_worker(
            self._load_notes(slug),
            exclusive=False,
            name="_load_notes",
        )
        viewer = self.query_one("#note-viewer", Markdown)
        viewer.update("*Note deleted.*")

    def action_refresh(self) -> None:
        self.run_worker(self._load_topics(), exclusive=True, name="_load_topics")
        if self._selected_topic is not None:
            slug = self._selected_topic.get("slug", "")
            self.run_worker(
                self._load_notes(slug), exclusive=False, name="_load_notes",
            )
