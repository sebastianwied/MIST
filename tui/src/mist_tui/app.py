"""MistApp: Textual layout shell with broker-connected agent tabs."""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Static, TabbedContent, TabPane

from mist_core.transport import DEFAULT_SOCKET_PATH

from .broker_client import BrokerClient
from .keybindings import GLOBAL_BINDINGS
from .messages import EditorResult, RequestFullScreenEditor
from .screens import EditorScreen
from .widget_loader import load_widget_class, parse_widget_specs
from .widgets.chat import ChatPanel

log = logging.getLogger(__name__)

BANNER = r"""  __  __ ___ ___ _____
 |  \/  |_ _/ __|_   _|
 | |\/| || |\__ \ | |
 |_|  |_|___|___/ |_|"""


class MistApp(App):
    """MIST TUI application shell."""

    ENABLE_COMMAND_PALETTE = False
    CSS_PATH = "mist_tui.tcss"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        socket_path: Path | str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._socket_path = Path(socket_path) if socket_path else DEFAULT_SOCKET_PATH
        self._catalog_client: BrokerClient | None = None
        self._widget_clients: list[BrokerClient] = []

    def compose(self) -> ComposeResult:
        yield Static(BANNER, id="banner")
        yield Static("Connecting...", id="status-bar")
        yield TabbedContent(id="agent-tabs")
        yield Footer()

    async def on_mount(self) -> None:
        await self._connect_and_mount()

    async def _connect_and_mount(self) -> None:
        status = self.query_one("#status-bar", Static)
        tabs = self.query_one("#agent-tabs", TabbedContent)

        try:
            # Catalog client just for listing agents
            self._catalog_client = BrokerClient(self._socket_path)
            await self._catalog_client.connect()
            catalog = await self._catalog_client.request_catalog()
        except Exception as exc:
            log.exception("failed to connect to broker")
            status.update(f"Connection failed: {exc}")
            return

        if not catalog:
            status.update("Connected | No agents registered")
            return

        for agent in catalog:
            agent_id = agent["agent_id"]
            agent_name = agent.get("name", agent_id)

            # Check if agent declares custom widgets
            widget_specs = parse_widget_specs(agent)
            widget_classes = []
            if widget_specs:
                for spec in widget_specs:
                    cls = load_widget_class(spec)
                    if cls is not None:
                        widget_classes.append((spec, cls))
                    else:
                        log.warning(
                            "failed to load widget %s for %s, skipping",
                            spec.id, agent_name,
                        )

            if widget_classes:
                # Mount each agent-declared widget as a tab
                for spec, cls in widget_classes:
                    client = BrokerClient(self._socket_path)
                    await client.connect()
                    self._widget_clients.append(client)

                    panel = cls(
                        broker_client=client,
                        agent_id=agent_id,
                        agent_name=agent_name,
                    )
                    tab_label = (
                        agent_name if spec.default
                        else f"{agent_name}: {spec.id}"
                    )
                    pane = TabPane(tab_label, panel)
                    await tabs.add_pane(pane)
            else:
                # Fall back to built-in ChatPanel
                client = BrokerClient(self._socket_path)
                await client.connect()
                self._widget_clients.append(client)

                panel = ChatPanel(
                    broker_client=client,
                    agent_id=agent_id,
                    agent_name=agent_name,
                )
                pane = TabPane(agent_name, panel)
                await tabs.add_pane(pane)

        count = len(catalog)
        status.update(f"Connected | {count} agent(s)")

    def on_request_full_screen_editor(
        self, message: RequestFullScreenEditor,
    ) -> None:
        """Handle a widget's request to open the full-screen editor."""
        screen = EditorScreen(
            content=message.content,
            file_path=message.file_path,
            title=message.title,
            metadata=message.metadata,
            read_only=message.read_only,
        )

        def _on_dismiss(result: EditorResult) -> None:
            if message.on_complete is not None:
                message.on_complete(result)

        self.push_screen(screen, _on_dismiss)

    async def action_quit(self) -> None:
        """Close all broker connections and exit."""
        for client in self._widget_clients:
            await client.close()
        if self._catalog_client is not None:
            await self._catalog_client.close()
        self.exit()
