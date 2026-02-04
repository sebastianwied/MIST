"""Tests for the full-screen EditorScreen."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button

from mist_tui.messages import EditorResult
from mist_tui.screens.editor_screen import EditorScreen


class EditorTestApp(App):
    """Minimal app that can push an EditorScreen and capture the result."""

    ENABLE_COMMAND_PALETTE = False

    def __init__(self, initial_content: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._initial_content = initial_content
        self.editor_result: EditorResult | None = None

    def compose(self) -> ComposeResult:
        yield Button("open", id="open-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        screen = EditorScreen(
            content=self._initial_content,
            title="Test Editor",
            metadata={"test": True},
        )
        self.push_screen(screen, self._on_dismiss)

    def _on_dismiss(self, result: EditorResult) -> None:
        self.editor_result = result


@pytest.mark.asyncio
async def test_editor_screen_composes():
    """EditorScreen composes without errors."""
    app = EditorTestApp()
    async with app.run_test() as pilot:
        await pilot.click("#open-btn")
        # Screen should now be active — check key widgets exist
        assert app.screen.query_one("#editor-textarea") is not None
        assert app.screen.query_one("#preview") is not None


@pytest.mark.asyncio
async def test_ctrl_s_saves():
    """Ctrl+S dismisses with saved=True and content."""
    app = EditorTestApp(initial_content="hello world")
    async with app.run_test() as pilot:
        await pilot.click("#open-btn")
        await pilot.press("ctrl+s")
        assert app.editor_result is not None
        assert app.editor_result.saved is True
        assert app.editor_result.content == "hello world"


@pytest.mark.asyncio
async def test_escape_cancels():
    """Escape dismisses with saved=False."""
    app = EditorTestApp(initial_content="some text")
    async with app.run_test() as pilot:
        await pilot.click("#open-btn")
        await pilot.press("escape")
        assert app.editor_result is not None
        assert app.editor_result.saved is False


@pytest.mark.asyncio
async def test_ctrl_p_toggles_preview():
    """Ctrl+P toggles preview visibility."""
    app = EditorTestApp()
    async with app.run_test() as pilot:
        await pilot.click("#open-btn")
        preview = app.screen.query_one("#preview")
        # Preview starts hidden (no 'visible' class)
        assert not preview.has_class("visible")

        await pilot.press("ctrl+p")
        assert preview.has_class("visible")

        await pilot.press("ctrl+p")
        assert not preview.has_class("visible")


@pytest.mark.asyncio
async def test_preview_updates_on_change():
    """When preview is visible, it updates as the TextArea content changes."""
    app = EditorTestApp(initial_content="initial")
    async with app.run_test() as pilot:
        await pilot.click("#open-btn")

        # Toggle preview on
        await pilot.press("ctrl+p")
        preview = app.screen.query_one("#preview")
        assert preview.has_class("visible")

        # Replace content in textarea
        textarea = app.screen.query_one("#editor-textarea")
        textarea.load_text("updated content")
        await pilot.pause()

        # The Markdown widget stores its source in ._markdown
        assert "updated content" in preview._markdown
