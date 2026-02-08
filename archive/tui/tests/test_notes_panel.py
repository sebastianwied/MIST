"""Tests for the NoteBrowserPanel widget."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from textual.app import App, ComposeResult
from textual.widgets import ListView

from mist_tui.messages import RequestFullScreenEditor
from mist_tui.widgets.notes import NoteBrowserPanel


# --- Fake broker ---


class FakeBroker:
    """Minimal mock that implements the broker methods used by NoteBrowserPanel."""

    def __init__(self) -> None:
        self._service_responses: dict[tuple[str, str], object] = {}

    def set_response(self, service: str, action: str, value: object) -> None:
        self._service_responses[(service, action)] = value

    async def request_service(
        self,
        service: str,
        action: str,
        params: dict | None = None,
        timeout: float = 10,
    ) -> object:
        return self._service_responses.get((service, action), [])

    async def send_command(self, agent_id: str, text: str, timeout: float = 30) -> str:
        return ""


SAMPLE_TOPICS = [
    {"id": "1", "name": "Work", "slug": "work", "created": "2025-01-01"},
    {"id": "2", "name": "Ideas", "slug": "ideas", "created": "2025-01-02"},
]

SAMPLE_NOTES = [
    {"id": "n1", "title": "First note"},
    {"id": "n2", "title": "Second note"},
]


class NotesPanelTestApp(App):
    """Host app for NoteBrowserPanel with a fake broker."""

    def __init__(self, broker: FakeBroker, **kwargs) -> None:
        super().__init__(**kwargs)
        self._broker = broker
        self.editor_requests: list[RequestFullScreenEditor] = []

    def compose(self) -> ComposeResult:
        panel = NoteBrowserPanel(
            broker_client=self._broker,  # type: ignore[arg-type]
            agent_id="test-agent",
            agent_name="Test",
        )
        yield panel

    def on_request_full_screen_editor(
        self, message: RequestFullScreenEditor,
    ) -> None:
        self.editor_requests.append(message)


@pytest.mark.asyncio
async def test_notes_panel_composes():
    """NoteBrowserPanel composes without errors."""
    broker = FakeBroker()
    broker.set_response("storage", "list_topics", SAMPLE_TOPICS)
    app = NotesPanelTestApp(broker)
    async with app.run_test():
        panel = app.query_one(NoteBrowserPanel)
        assert panel is not None
        assert app.query_one("#topic-list") is not None
        assert app.query_one("#note-list") is not None
        assert app.query_one("#note-viewer") is not None


@pytest.mark.asyncio
async def test_topic_list_populates():
    """Topic list is populated from the broker service."""
    broker = FakeBroker()
    broker.set_response("storage", "list_topics", SAMPLE_TOPICS)
    app = NotesPanelTestApp(broker)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()  # Wait for worker to complete
        topic_list = app.query_one("#topic-list", ListView)
        assert len(topic_list) == 2


@pytest.mark.asyncio
async def test_note_list_populates_on_topic_select():
    """Note list populates when a topic is selected."""
    broker = FakeBroker()
    broker.set_response("storage", "list_topics", SAMPLE_TOPICS)
    broker.set_response("storage", "list_notes", SAMPLE_NOTES)
    app = NotesPanelTestApp(broker)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()

        # Select first topic
        topic_list = app.query_one("#topic-list", ListView)
        topic_list.index = 0
        topic_list.action_select_cursor()
        await pilot.pause()
        await pilot.pause()

        note_list = app.query_one("#note-list", ListView)
        assert len(note_list) == 2


@pytest.mark.asyncio
async def test_new_button_posts_editor_request():
    """New button posts RequestFullScreenEditor when a topic is selected."""
    broker = FakeBroker()
    broker.set_response("storage", "list_topics", SAMPLE_TOPICS)
    app = NotesPanelTestApp(broker)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()

        # Select a topic first
        topic_list = app.query_one("#topic-list", ListView)
        topic_list.index = 0
        topic_list.action_select_cursor()
        await pilot.pause()

        # Click New button
        await pilot.click("#btn-new")
        await pilot.pause()

        assert len(app.editor_requests) == 1
        req = app.editor_requests[0]
        assert req.content == ""
        assert req.metadata["action"] == "new"
        assert req.metadata["topic_slug"] == "work"
