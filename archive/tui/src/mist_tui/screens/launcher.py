"""Launcher screen: start broker and agents before entering the main TUI."""

from __future__ import annotations

from dataclasses import dataclass, field

from textual.app import ComposeResult
from textual.containers import Center, Vertical
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Label, Static

from ..discovery import discover_agents
from ..process_manager import ProcessManager


@dataclass
class LaunchResult:
    """What the launcher started."""
    broker_started: bool = False
    agents_started: list[str] = field(default_factory=list)
    skipped: bool = False


class LauncherScreen(Screen[LaunchResult]):
    """Startup screen that discovers agents and offers to launch them."""

    DEFAULT_CSS = """
    LauncherScreen {
        align: center middle;
    }

    #launcher-box {
        width: 60;
        height: auto;
        border: round $primary;
        padding: 1 2;
    }

    #launcher-title {
        text-style: bold;
        width: 1fr;
        text-align: center;
        margin-bottom: 1;
    }

    #broker-status {
        margin-bottom: 1;
    }

    #agents-section {
        margin-bottom: 1;
    }

    .agent-checkbox {
        margin-left: 2;
    }

    #button-row {
        width: 1fr;
        align: center middle;
        height: auto;
        margin-top: 1;
    }

    #button-row Button {
        margin: 0 1;
    }
    """

    def __init__(self, process_manager: ProcessManager) -> None:
        super().__init__()
        self._pm = process_manager
        self._agents = discover_agents()
        self._broker_already_running = process_manager.broker_running()

    def compose(self) -> ComposeResult:
        with Vertical(id="launcher-box"):
            yield Static("MIST Launcher", id="launcher-title")

            if self._broker_already_running:
                yield Label("Broker: [green]Running[/green]", id="broker-status")
            else:
                yield Label("Broker: [red]Not running[/red] (will start)", id="broker-status")

            with Vertical(id="agents-section"):
                if self._agents:
                    yield Label("Agents:")
                    for agent in self._agents:
                        name = agent.get("name", "unknown")
                        desc = agent.get("description", "")
                        label = f"{name} — {desc}" if desc else name
                        yield Checkbox(
                            label,
                            value=True,
                            id=f"agent-{name}",
                            classes="agent-checkbox",
                        )
                else:
                    yield Label("[dim]No agents discovered[/dim]")

            with Center(id="button-row"):
                yield Button("Launch", variant="primary", id="btn-launch")
                yield Button("Skip", variant="default", id="btn-skip")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-skip":
            self.dismiss(LaunchResult(skipped=True))
            return

        if event.button.id == "btn-launch":
            result = LaunchResult()

            # Start broker if not already running
            if not self._broker_already_running:
                try:
                    self._pm.start_broker()
                    result.broker_started = True
                except Exception as exc:
                    self.app.notify(
                        f"Failed to start broker: {exc}",
                        severity="error",
                    )
                    return

            # Start checked agents
            for agent in self._agents:
                name = agent.get("name", "unknown")
                cb = self.query_one(f"#agent-{name}", Checkbox)
                if cb.value:
                    try:
                        self._pm.start_agent(agent["command"])
                        result.agents_started.append(name)
                    except Exception as exc:
                        self.app.notify(
                            f"Failed to start {name}: {exc}",
                            severity="error",
                        )

            self.dismiss(result)
