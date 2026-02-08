"""Tests for the SidePanelEditor widget."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from mist_tui.widgets.editor import SidePanelEditor


class SidePanelTestApp(App):
    """Minimal host for a SidePanelEditor."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.saved_events: list[SidePanelEditor.EditorSaved] = []
        self.cancelled_events: list[SidePanelEditor.EditorCancelled] = []

    def compose(self) -> ComposeResult:
        yield SidePanelEditor(id="editor")

    def on_side_panel_editor_editor_saved(
        self, event: SidePanelEditor.EditorSaved,
    ) -> None:
        self.saved_events.append(event)

    def on_side_panel_editor_editor_cancelled(
        self, event: SidePanelEditor.EditorCancelled,
    ) -> None:
        self.cancelled_events.append(event)


@pytest.mark.asyncio
async def test_starts_hidden():
    """SidePanelEditor starts hidden (no 'open' class)."""
    app = SidePanelTestApp()
    async with app.run_test():
        editor = app.query_one("#editor", SidePanelEditor)
        assert not editor.has_class("open")


@pytest.mark.asyncio
async def test_open_makes_visible():
    """open() adds the 'open' class and loads content."""
    app = SidePanelTestApp()
    async with app.run_test() as pilot:
        editor = app.query_one("#editor", SidePanelEditor)
        editor.open(content="loaded text", title="My Note")
        await pilot.pause()

        assert editor.has_class("open")
        textarea = editor.query_one("#side-editor-textarea")
        assert textarea.text == "loaded text"


@pytest.mark.asyncio
async def test_close_hides():
    """close() removes the 'open' class."""
    app = SidePanelTestApp()
    async with app.run_test() as pilot:
        editor = app.query_one("#editor", SidePanelEditor)
        editor.open(content="text")
        await pilot.pause()
        assert editor.has_class("open")

        editor.close()
        await pilot.pause()
        assert not editor.has_class("open")


@pytest.mark.asyncio
async def test_ctrl_s_posts_editor_saved():
    """Ctrl+S posts EditorSaved with current content."""
    app = SidePanelTestApp()
    async with app.run_test() as pilot:
        editor = app.query_one("#editor", SidePanelEditor)
        editor.open(
            content="save me",
            file_path="/tmp/test.md",
            metadata={"key": "val"},
        )
        await pilot.pause()

        # Focus the textarea and trigger save
        editor.query_one("#side-editor-textarea").focus()
        await pilot.press("ctrl+s")
        await pilot.pause()

        assert len(app.saved_events) == 1
        ev = app.saved_events[0]
        assert ev.content == "save me"
        assert ev.file_path == "/tmp/test.md"
        assert ev.metadata == {"key": "val"}
        # Should auto-close after save
        assert not editor.has_class("open")


@pytest.mark.asyncio
async def test_escape_posts_editor_cancelled():
    """Escape posts EditorCancelled."""
    app = SidePanelTestApp()
    async with app.run_test() as pilot:
        editor = app.query_one("#editor", SidePanelEditor)
        editor.open(content="cancel me")
        await pilot.pause()

        editor.query_one("#side-editor-textarea").focus()
        await pilot.press("escape")
        await pilot.pause()

        assert len(app.cancelled_events) == 1
        # Should auto-close after cancel
        assert not editor.has_class("open")
