"""Demo app for testing editor widgets without a running broker."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Static

from .messages import EditorResult, RequestFullScreenEditor
from .screens import EditorScreen
from .widgets.editor import SidePanelEditor

SAMPLE_MARKDOWN = """\
# Sample Note

This is a **demo note** for testing the editor.

## Features

- **Ctrl+P** toggle markdown preview
- **Ctrl+S** save and close
- **Escape** cancel and close

## Code Example

```python
def hello():
    print("Hello from MIST")
```

Try editing this content!
"""


class DemoApp(App):
    """Standalone demo for editor widgets — no broker required."""

    ENABLE_COMMAND_PALETTE = False

    DEFAULT_CSS = """
    #demo-header {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
        text-style: bold;
    }
    #demo-body {
        height: 1fr;
    }
    #demo-buttons {
        width: 30;
        padding: 1 2;
    }
    #demo-buttons Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    #demo-result {
        height: auto;
        max-height: 6;
        padding: 0 1;
        color: $text-muted;
    }
    #side-editor-container {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "MIST Editor Demo — no broker needed", id="demo-header",
        )
        with Horizontal(id="demo-body"):
            with Vertical(id="demo-buttons"):
                yield Button(
                    "Full-Screen Editor", id="btn-fullscreen", variant="primary",
                )
                yield Button("Side Panel Editor", id="btn-side")
                yield Button("Close Side Panel", id="btn-side-close")
            with Vertical(id="side-editor-container"):
                yield SidePanelEditor(id="side-editor")
        yield Static("", id="demo-result")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-fullscreen":
            self.push_screen(
                EditorScreen(
                    content=SAMPLE_MARKDOWN,
                    title="Demo Editor",
                    metadata={"source": "demo"},
                ),
                self._on_editor_dismiss,
            )
        elif event.button.id == "btn-side":
            editor = self.query_one("#side-editor", SidePanelEditor)
            editor.open(
                content=SAMPLE_MARKDOWN,
                title="Side Panel Demo",
                metadata={"source": "demo"},
            )
        elif event.button.id == "btn-side-close":
            editor = self.query_one("#side-editor", SidePanelEditor)
            editor.close()

    def _on_editor_dismiss(self, result: EditorResult) -> None:
        status = self.query_one("#demo-result", Static)
        if result.saved:
            lines = result.content.count("\n") + 1
            status.update(f"Saved ({lines} lines, {len(result.content)} chars)")
        else:
            status.update("Cancelled")

    def on_side_panel_editor_editor_saved(
        self, event: SidePanelEditor.EditorSaved,
    ) -> None:
        status = self.query_one("#demo-result", Static)
        lines = event.content.count("\n") + 1
        status.update(
            f"Side panel saved ({lines} lines, {len(event.content)} chars)"
        )

    def on_side_panel_editor_editor_cancelled(
        self, event: SidePanelEditor.EditorCancelled,
    ) -> None:
        status = self.query_one("#demo-result", Static)
        status.update("Side panel cancelled")
