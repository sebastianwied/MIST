"""Custom Textual messages for editor communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from textual.message import Message


@dataclass
class EditorResult:
    """Result returned when an editor screen is dismissed."""

    saved: bool
    content: str
    file_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RequestFullScreenEditor(Message):
    """Posted by any widget to request a full-screen editor overlay.

    The app catches this and pushes an ``EditorScreen``.
    """

    def __init__(
        self,
        content: str = "",
        file_path: str | None = None,
        title: str = "Editor",
        on_complete: Callable[[EditorResult], None] | None = None,
        metadata: dict[str, Any] | None = None,
        read_only: bool = False,
    ) -> None:
        super().__init__()
        self.content = content
        self.file_path = file_path
        self.title = title
        self.on_complete = on_complete
        self.metadata = metadata or {}
        self.read_only = read_only
