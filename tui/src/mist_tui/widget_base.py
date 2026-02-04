"""Base class for broker-connected TUI widgets."""

from __future__ import annotations

from typing import Any, Callable

from textual.widget import Widget

from .broker_client import BrokerClient
from .messages import EditorResult, RequestFullScreenEditor


class BrokerWidget(Widget):
    """Widget that communicates with an agent via a BrokerClient.

    Subclasses use ``self.broker`` to send commands and service requests.
    """

    def __init__(
        self,
        broker_client: BrokerClient,
        agent_id: str,
        agent_name: str,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._broker = broker_client
        self._agent_id = agent_id
        self._agent_name = agent_name

    @property
    def broker(self) -> BrokerClient:
        return self._broker

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def agent_name(self) -> str:
        return self._agent_name

    def request_editor(
        self,
        content: str = "",
        file_path: str | None = None,
        title: str = "Editor",
        on_complete: Callable[[EditorResult], None] | None = None,
        metadata: dict[str, Any] | None = None,
        read_only: bool = False,
    ) -> None:
        """Post a message requesting the app open a full-screen editor."""
        self.post_message(
            RequestFullScreenEditor(
                content=content,
                file_path=file_path,
                title=title,
                on_complete=on_complete,
                metadata=metadata,
                read_only=read_only,
            )
        )
