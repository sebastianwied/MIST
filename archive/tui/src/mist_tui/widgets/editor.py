"""Inline side-panel editor widget."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, TextArea


class SidePanelEditor(Widget):
    """Reusable inline editor that can be embedded in any widget.

    Posts ``EditorSaved`` or ``EditorCancelled`` messages that bubble
    to the parent widget.  The parent is responsible for persistence.
    """

    DEFAULT_CSS = """
    SidePanelEditor {
        display: none;
        height: 1fr;
        layout: vertical;
    }
    SidePanelEditor.open {
        display: block;
    }
    SidePanelEditor #side-editor-title {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    SidePanelEditor TextArea {
        height: 1fr;
    }
    SidePanelEditor #side-editor-hint {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("f3", "switch_mode", "Full Screen", show=True),
    ]

    class EditorSwitchMode(Message):
        """Posted when the user wants to switch to full-screen mode."""

        def __init__(
            self,
            content: str,
            file_path: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            super().__init__()
            self.content = content
            self.file_path = file_path
            self.metadata = metadata or {}

    class EditorSaved(Message):
        """Posted when the user saves (Ctrl+S)."""

        def __init__(
            self,
            content: str,
            file_path: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            super().__init__()
            self.content = content
            self.file_path = file_path
            self.metadata = metadata or {}

    class EditorCancelled(Message):
        """Posted when the user cancels (Escape)."""

        def __init__(
            self,
            file_path: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            super().__init__()
            self.file_path = file_path
            self.metadata = metadata or {}

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._file_path: str | None = None
        self._title: str = "Editor"
        self._metadata: dict[str, Any] = {}
        self._read_only: bool = False

    def compose(self) -> ComposeResult:
        yield Static("Editor", id="side-editor-title")
        yield TextArea("", language="markdown", id="side-editor-textarea")
        yield Static(
            "Ctrl+S save | Escape cancel | F3 full screen",
            id="side-editor-hint",
        )

    def open(
        self,
        content: str = "",
        file_path: str | None = None,
        title: str = "Editor",
        metadata: dict[str, Any] | None = None,
        read_only: bool = False,
    ) -> None:
        """Show the editor and load content."""
        self._file_path = file_path
        self._title = title
        self._metadata = metadata or {}
        self._read_only = read_only
        self.add_class("open")
        self.query_one("#side-editor-title", Static).update(title)
        textarea = self.query_one("#side-editor-textarea", TextArea)
        textarea.read_only = read_only
        textarea.load_text(content)
        textarea.focus()
        hint = "Escape close | F3 full screen" if read_only else "Ctrl+S save | Escape cancel | F3 full screen"
        self.query_one("#side-editor-hint", Static).update(hint)

    def close(self) -> None:
        """Hide the editor."""
        self.remove_class("open")

    def action_save(self) -> None:
        if self._read_only:
            return
        content = self.query_one("#side-editor-textarea", TextArea).text
        self.post_message(
            self.EditorSaved(
                content=content,
                file_path=self._file_path,
                metadata=self._metadata,
            )
        )
        self.close()

    def action_switch_mode(self) -> None:
        content = self.query_one("#side-editor-textarea", TextArea).text
        self.post_message(
            self.EditorSwitchMode(
                content=content,
                file_path=self._file_path,
                metadata=self._metadata,
            )
        )
        self.close()

    def action_cancel(self) -> None:
        self.post_message(
            self.EditorCancelled(
                file_path=self._file_path,
                metadata=self._metadata,
            )
        )
        self.close()
