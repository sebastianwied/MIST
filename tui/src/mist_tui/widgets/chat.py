"""Built-in generic chat widget for any broker-connected agent."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, RichLog, Static
from textual.worker import Worker, WorkerState

from ..widget_base import BrokerWidget


class ChatPanel(BrokerWidget):
    """Generic chat panel that works with any agent.

    Displays a chat log, activity indicator, and text input.
    Widget IDs are namespaced with ``agent_id`` so multiple
    ChatPanels can coexist.
    """

    DEFAULT_CSS = """
    ChatPanel {
        height: 1fr;
        layout: vertical;
    }
    ChatPanel RichLog {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    ChatPanel .activity {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    ChatPanel Input {
        dock: bottom;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield RichLog(
                id=f"log-{self._agent_id}", highlight=True, markup=True,
            )
            yield Static(
                "", id=f"activity-{self._agent_id}", classes="activity",
            )
            yield Input(
                placeholder=f"Message {self._agent_name}...",
                id=f"input-{self._agent_id}",
            )

    def on_mount(self) -> None:
        log_widget = self.query_one(f"#log-{self._agent_id}", RichLog)
        log_widget.write(f"[bold]Connected to {self._agent_name}[/bold]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return

        inp = self.query_one(f"#input-{self._agent_id}", Input)
        log_widget = self.query_one(f"#log-{self._agent_id}", RichLog)
        activity = self.query_one(f"#activity-{self._agent_id}", Static)

        # Echo user input
        log_widget.write(f"[bold cyan]> {text}[/bold cyan]")
        inp.value = ""
        inp.disabled = True
        activity.update("thinking...")

        self.run_worker(self._send_command(text), exclusive=True)

    async def _send_command(self, text: str) -> str:
        return await self.broker.send_command(self.agent_id, text)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.name != "_send_command":
            return

        inp = self.query_one(f"#input-{self._agent_id}", Input)
        activity = self.query_one(f"#activity-{self._agent_id}", Static)
        log_widget = self.query_one(f"#log-{self._agent_id}", RichLog)

        if event.state == WorkerState.SUCCESS:
            result = event.worker.result
            for line in result.split("\n"):
                log_widget.write(Text(line))
            activity.update("")
            inp.disabled = False
            inp.focus()
        elif event.state == WorkerState.ERROR:
            error = event.worker.error
            log_widget.write(f"\n[bold red]Error: {error}[/bold red]")
            activity.update("")
            inp.disabled = False
            inp.focus()
