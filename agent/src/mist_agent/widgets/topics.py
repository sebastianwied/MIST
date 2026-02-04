"""Read-only topic browser widget for MIST."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, ListView, ListItem, Label, RichLog, Static
from textual.worker import Worker, WorkerState

from mist_tui.widget_base import BrokerWidget


class TopicsPanel(BrokerWidget):
    """Browse topics and view their synthesis."""

    DEFAULT_CSS = """
    TopicsPanel {
        height: 1fr;
        layout: vertical;
    }
    TopicsPanel ListView {
        height: 1fr;
        border: solid $primary-darken-2;
    }
    TopicsPanel RichLog {
        height: 2fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    TopicsPanel .header-bar {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    TopicsPanel Button {
        min-width: 10;
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Topics", classes="header-bar")
            yield ListView(id=f"topic-list-{self._agent_id}")
            yield RichLog(
                id=f"topic-detail-{self._agent_id}",
                highlight=True,
                markup=True,
                wrap=True,
            )
            yield Button("Refresh", id=f"topic-refresh-{self._agent_id}")

    def on_mount(self) -> None:
        self._load_topics()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == f"topic-refresh-{self._agent_id}":
            self._load_topics()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        slug = event.item.name
        if slug:
            self.run_worker(
                self._fetch_synthesis(slug),
                name="fetch_synthesis",
                exclusive=True,
            )

    def _load_topics(self) -> None:
        self.run_worker(
            self._fetch_topic_index(),
            name="fetch_topics",
            exclusive=True,
        )

    async def _fetch_topic_index(self) -> list[dict]:
        result = await self.broker.request_service(
            "storage", "load_topic_index",
        )
        return result if isinstance(result, list) else []

    async def _fetch_synthesis(self, slug: str) -> str:
        result = await self.broker.request_service(
            "storage", "load_topic_synthesis", {"slug": slug},
        )
        return result if isinstance(result, str) else ""

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state != WorkerState.SUCCESS:
            if event.state == WorkerState.ERROR:
                detail = self.query_one(
                    f"#topic-detail-{self._agent_id}", RichLog,
                )
                detail.write(
                    f"[bold red]Error: {event.worker.error}[/bold red]",
                )
            return

        if event.worker.name == "fetch_topics":
            topics = event.worker.result
            lv = self.query_one(f"#topic-list-{self._agent_id}", ListView)
            lv.clear()
            if not topics:
                lv.append(ListItem(Label("[dim]No topics yet[/dim]")))
                return
            for t in topics:
                slug = t.get("slug", "")
                name = t.get("name", slug)
                item = ListItem(Label(f"{name} ({slug})"), name=slug)
                lv.append(item)
            return

        if event.worker.name == "fetch_synthesis":
            text = event.worker.result
            detail = self.query_one(
                f"#topic-detail-{self._agent_id}", RichLog,
            )
            detail.clear()
            if text:
                detail.write(text)
            else:
                detail.write("[dim]No synthesis yet for this topic.[/dim]")
            return
