"""Global keybinding constants for the TUI."""

from textual.binding import Binding

GLOBAL_BINDINGS: list[Binding] = [
    Binding("ctrl+q", "quit", "Quit", show=True),
]
