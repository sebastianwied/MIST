"""Full-screen markdown editor with optional live preview."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, Markdown, TextArea

from ..messages import EditorResult


class EditorScreen(Screen[EditorResult]):
    """Push/pop full-screen editor.

    Returns an ``EditorResult`` via ``dismiss()`` so the caller can
    inspect whether the user saved or cancelled.
    """

    DEFAULT_CSS = """
    EditorScreen {
        layout: vertical;
    }
    EditorScreen #editor-pane {
        height: 1fr;
    }
    EditorScreen TextArea {
        width: 1fr;
    }
    EditorScreen #preview {
        width: 1fr;
        border-left: solid $primary-darken-2;
        padding: 0 1;
        display: none;
    }
    EditorScreen #preview.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("ctrl+p", "toggle_preview", "Preview", show=True, priority=True),
        Binding("f3", "switch_mode", "Side View", show=True),
    ]

    def __init__(
        self,
        content: str = "",
        file_path: str | None = None,
        title: str = "Editor",
        metadata: dict | None = None,
        read_only: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._initial_content = content
        self._file_path = file_path
        self._title = title
        self._metadata = metadata or {}
        self._read_only = read_only

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="editor-pane"):
            yield TextArea(
                self._initial_content,
                language="markdown",
                id="editor-textarea",
            )
            yield Markdown(
                self._initial_content,
                id="preview",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.title = self._title
        textarea = self.query_one("#editor-textarea", TextArea)
        textarea.read_only = self._read_only
        textarea.focus()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        preview = self.query_one("#preview", Markdown)
        if preview.has_class("visible"):
            preview.update(event.text_area.text)

    def action_save(self) -> None:
        if self._read_only:
            return
        content = self.query_one("#editor-textarea", TextArea).text
        self.dismiss(
            EditorResult(
                saved=True,
                content=content,
                file_path=self._file_path,
                metadata=self._metadata,
            )
        )

    def action_cancel(self) -> None:
        self.dismiss(
            EditorResult(
                saved=False,
                content="",
                file_path=self._file_path,
                metadata=self._metadata,
            )
        )

    def action_switch_mode(self) -> None:
        content = self.query_one("#editor-textarea", TextArea).text
        self.dismiss(
            EditorResult(
                saved=False,
                content=content,
                file_path=self._file_path,
                metadata={**self._metadata, "switch_mode": True},
            )
        )

    def action_toggle_preview(self) -> None:
        preview = self.query_one("#preview", Markdown)
        preview.toggle_class("visible")
        if preview.has_class("visible"):
            content = self.query_one("#editor-textarea", TextArea).text
            preview.update(content)
