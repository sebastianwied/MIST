"""MIST-specific chat widget with persona and aggregate state machines."""

from __future__ import annotations

import json
from enum import Enum, auto
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, RichLog, Static, TextArea
from textual.worker import Worker, WorkerState

from mist_tui.messages import EditorResult
from mist_tui.widget_base import BrokerWidget
from mist_tui.widgets.editor import SidePanelEditor


class _Mode(Enum):
    NORMAL = auto()
    PERSONA_EDIT = auto()
    PERSONA_CONFIRM = auto()
    AGGREGATE_CONFIRM = auto()


class MistChatPanel(BrokerWidget):
    """MIST chat panel with persona editing and aggregate confirmation flows."""

    DEFAULT_CSS = """
    MistChatPanel {
        height: 1fr;
        layout: vertical;
    }
    MistChatPanel RichLog {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    MistChatPanel .activity {
        height: 1;
        color: $text-muted;
        padding: 0 1;
    }
    MistChatPanel Input {
        dock: bottom;
    }
    MistChatPanel .viewer {
        display: none;
        width: 40%;
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    MistChatPanel SidePanelEditor {
        width: 50%;
    }
    """

    _ACTIVITY_LABELS: dict[str, str] = {
        "recall": "Recalling...",
        "aggregate": "Aggregating...",
        "sync": "Synthesizing...",
        "resynth": "Resynthesizing...",
        "synthesis": "Synthesizing topic...",
    }

    _NO_ACTIVITY_COMMANDS: set[str] = {
        "task", "event", "note", "notes", "view", "edit", "status",
        "settings", "set", "help", "stop", "tasks", "events", "debug",
    }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._mode = _Mode.NORMAL
        self._persona_draft: str = ""
        self._persona_working: str = ""
        # Aggregate state
        self._agg_proposals: list[str] = []
        self._agg_current_idx: int = 0
        self._agg_confirmed: dict[str, str] = {}
        self._agg_skipped: set[str] = set()
        self._agg_assignments: list[dict] = []
        self._view_arg: str = ""
        self._editor_mode: str = "full"
        self._view_content: str = ""
        self._view_title: str = ""
        self._view_read_only: bool = False
        self._note_slug: str = ""
        self._note_filename: str = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id=f"main-{self._agent_id}"):
                yield RichLog(
                    id=f"log-{self._agent_id}",
                    highlight=True,
                    markup=True,
                    wrap=True,
                )
                yield SidePanelEditor(id=f"side-editor-{self._agent_id}")
            yield Static(
                "", id=f"activity-{self._agent_id}", classes="activity",
            )
            yield Input(
                placeholder=f"Message {self._agent_name}...",
                id=f"input-{self._agent_id}",
            )

    def on_mount(self) -> None:
        log_w = self.query_one(f"#log-{self._agent_id}", RichLog)
        log_w.write(f"[bold]Connected to {self._agent_name}[/bold]")

    # ── helpers ──────────────────────────────────────────────────────

    def _log_write(self, text: str) -> None:
        self.query_one(f"#log-{self._agent_id}", RichLog).write(text)

    def _log_write_plain(self, text: str) -> None:
        from rich.text import Text as RichText
        self.query_one(f"#log-{self._agent_id}", RichLog).write(RichText(text))

    def _log_write_md(self, text: str) -> None:
        from rich.markdown import Markdown as RichMarkdown
        self.query_one(f"#log-{self._agent_id}", RichLog).write(
            RichMarkdown(text),
        )

    def _set_activity(self, msg: str) -> None:
        self.query_one(f"#activity-{self._agent_id}", Static).update(
            f"  {msg}",
        )

    def _clear_activity(self) -> None:
        self.query_one(f"#activity-{self._agent_id}", Static).update("")

    def _set_busy(self, busy: bool) -> None:
        inp = self.query_one(f"#input-{self._agent_id}", Input)
        inp.disabled = busy
        if not busy:
            inp.focus()

    # ── input dispatch ───────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.clear()

        # ── persona state machine ────────────────────────────────────
        if self._mode == _Mode.PERSONA_EDIT:
            self._on_persona_edit(text)
            return

        if self._mode == _Mode.PERSONA_CONFIRM:
            self._on_persona_confirm(text)
            return

        # ── aggregate confirm state machine ──────────────────────────
        if self._mode == _Mode.AGGREGATE_CONFIRM:
            self._on_aggregate_confirm(text)
            return

        # ── normal mode ──────────────────────────────────────────────
        self._log_write(f"[bold cyan]> {text}[/bold cyan]")

        cmd = text.split()[0].lower() if text.split() else ""

        # persona → enter edit mode via broker
        if text.strip().lower() == "persona":
            self._set_busy(True)
            self._set_activity("Loading persona...")
            self.run_worker(
                self._cmd_persona_get(), name="persona_get", exclusive=True,
            )
            return

        # aggregate → classify via broker
        if text.strip().lower() == "aggregate":
            self._set_busy(True)
            self._set_activity("Aggregating...")
            self.run_worker(
                self._cmd_aggregate_classify(),
                name="aggregate_classify",
                exclusive=True,
            )
            return

        # view → display in-panel (via broker service)
        if cmd == "view":
            arg = text[len("view"):].strip()
            if arg:
                self._view_arg = arg
                self._set_busy(True)
                self.run_worker(
                    self._cmd_view(arg), name="view", exclusive=True,
                )
            else:
                self.run_worker(
                    self._cmd_normal(text), name="dispatch", exclusive=True,
                )
            return

        # note new / note edit → create or open file in editor
        if cmd == "note":
            parts = text.split(None, 2)
            if len(parts) >= 2 and parts[1].lower() in ("new", "edit", "promote"):
                self._set_busy(True)
                self.run_worker(
                    self._cmd_normal(text), name="note_new", exclusive=True,
                )
                return

        # edit → open in-panel editor (read-write)
        if cmd == "edit":
            arg = text[len("edit"):].strip()
            if arg:
                self._view_arg = arg
                self._set_busy(True)
                self.run_worker(
                    self._cmd_edit(arg), name="edit", exclusive=True,
                )
            else:
                self.run_worker(
                    self._cmd_normal(text), name="dispatch", exclusive=True,
                )
            return

        # everything else → normal command dispatch
        self._set_busy(True)
        label = self._ACTIVITY_LABELS.get(cmd)
        if label is None and cmd not in self._NO_ACTIVITY_COMMANDS:
            label = "Thinking..."
        if label:
            self._set_activity(label)
        self.run_worker(
            self._cmd_normal(text), name="dispatch", exclusive=True,
        )

    # ── persona flow ─────────────────────────────────────────────────

    def _on_persona_edit(self, text: str) -> None:
        if text.lower() == "done":
            self._mode = _Mode.NORMAL
            self._log_write("[dim]Persona editing cancelled.[/dim]")
            return
        self._log_write(f"[cyan]persona>[/cyan] {text}")
        self._set_busy(True)
        self._set_activity("Generating persona...")
        self.run_worker(
            self._cmd_persona_draft(text),
            name="persona_draft",
            exclusive=True,
        )

    def _on_persona_confirm(self, text: str) -> None:
        choice = text.lower()
        if choice == "yes":
            self._set_busy(True)
            self._set_activity("Saving persona...")
            self.run_worker(
                self._cmd_persona_save(self._persona_draft),
                name="persona_save",
                exclusive=True,
            )
        elif choice == "no":
            self._log_write("[yellow]Draft discarded.[/yellow]")
            self._mode = _Mode.PERSONA_EDIT
            self._log_write(
                "[dim]Describe another change, or type 'done' to exit.[/dim]",
            )
        else:
            # Further refinement
            self._persona_working = self._persona_draft
            self._log_write(f"[cyan]persona>[/cyan] {text}")
            self._set_busy(True)
            self._set_activity("Generating persona...")
            self.run_worker(
                self._cmd_persona_draft(text),
                name="persona_draft",
                exclusive=True,
            )

    # ── aggregate flow ───────────────────────────────────────────────

    def _on_aggregate_confirm(self, text: str) -> None:
        name = self._agg_proposals[self._agg_current_idx]
        choice = text.strip()
        if choice.lower() == "no":
            self._agg_skipped.add(name)
        elif choice.lower() == "yes":
            self._agg_confirmed[name] = "yes"
        else:
            self._agg_confirmed[name] = choice  # renamed

        self._agg_current_idx += 1
        if self._agg_current_idx < len(self._agg_proposals):
            next_name = self._agg_proposals[self._agg_current_idx]
            self._log_write(
                f"[dim]Create topic '{next_name}'? (yes / no / type new name)[/dim]",
            )
        else:
            self._mode = _Mode.NORMAL
            self._set_busy(True)
            self._set_activity("Routing entries...")
            self.run_worker(
                self._cmd_aggregate_route(),
                name="aggregate_route",
                exclusive=True,
            )

    # ── broker command workers ───────────────────────────────────────

    async def _cmd_normal(self, text: str) -> str:
        return await self.broker.send_command(self.agent_id, text)

    async def _cmd_view(self, name: str) -> str:
        return await self.broker.send_command(self.agent_id, f"view {name}")

    async def _cmd_edit(self, name: str) -> str:
        return await self.broker.send_command(self.agent_id, f"edit {name}")

    async def _cmd_edit_save(self, name: str, content: str) -> str:
        return await self.broker.send_command(
            self.agent_id, f"edit:save {name} {content}",
        )

    async def _cmd_note_save(self, slug: str, filename: str, content: str) -> str:
        return await self.broker.send_command(
            self.agent_id, f"note:save {slug} {filename} {content}",
        )

    async def _cmd_persona_get(self) -> str:
        return await self.broker.send_command(self.agent_id, "persona:get")

    async def _cmd_persona_draft(self, user_input: str) -> str:
        return await self.broker.send_command(
            self.agent_id, f"persona:draft {user_input}",
        )

    async def _cmd_persona_save(self, persona_text: str) -> str:
        return await self.broker.send_command(
            self.agent_id, f"persona:save {persona_text}",
        )

    async def _cmd_aggregate_classify(self) -> str:
        return await self.broker.send_command(
            self.agent_id, "aggregate:classify", timeout=60.0,
        )

    async def _cmd_aggregate_route(self) -> str:
        payload = json.dumps({
            "assignments": self._agg_assignments,
            "confirmed": self._agg_confirmed,
            "skipped": list(self._agg_skipped),
        })
        return await self.broker.send_command(
            self.agent_id, f"aggregate:route {payload}", timeout=30.0,
        )

    # ── worker results ───────────────────────────────────────────────

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.ERROR:
            error = event.worker.error
            self._log_write(f"[bold red]Error: {error}[/bold red]")
            self._clear_activity()
            self._set_busy(False)
            return

        if event.state != WorkerState.SUCCESS:
            return

        result = event.worker.result
        name = event.worker.name

        if name == "persona_get":
            self._persona_working = result
            self._log_write("[bold]--- Current Persona ---[/bold]")
            self._log_write(result)
            self._log_write("[bold]-----------------------[/bold]")
            self._log_write(
                "[dim]Describe what you'd like to change, or type 'done' to exit.[/dim]",
            )
            self._mode = _Mode.PERSONA_EDIT
            self._clear_activity()
            self._set_busy(False)
            return

        if name == "persona_draft":
            self._persona_draft = result
            self._log_write("[bold]--- Proposed Persona ---[/bold]")
            self._log_write(result)
            self._log_write("[bold]------------------------[/bold]")
            self._log_write(
                "[dim]Apply this persona? (yes / no / describe more changes)[/dim]",
            )
            self._mode = _Mode.PERSONA_CONFIRM
            self._clear_activity()
            self._set_busy(False)
            return

        if name == "persona_save":
            self._log_write("[green]Persona updated and saved.[/green]")
            self._mode = _Mode.NORMAL
            self._clear_activity()
            self._set_busy(False)
            return

        if name == "aggregate_classify":
            self._clear_activity()
            try:
                data = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                self._log_write(
                    "Could not parse classification response. Try again.",
                )
                self._set_busy(False)
                return

            entries_count = data.get("entries", 0)
            if entries_count == 0:
                self._log_write("No entries to aggregate.")
                self._set_busy(False)
                return

            self._agg_assignments = data.get("assignments", [])
            if not self._agg_assignments:
                self._log_write(
                    "Could not parse LLM classification. Try again.",
                )
                self._set_busy(False)
                return

            proposals = data.get("proposals", {})
            self._agg_proposals = list(proposals.keys())
            self._agg_current_idx = 0
            self._agg_confirmed = {}
            self._agg_skipped = set()

            if self._agg_proposals:
                self._mode = _Mode.AGGREGATE_CONFIRM
                name_0 = self._agg_proposals[0]
                self._log_write(
                    f"[dim]Create topic '{name_0}'? (yes / no / type new name)[/dim]",
                )
                self._set_busy(False)
            else:
                # No new topics — go straight to routing
                self._set_activity("Routing entries...")
                self.run_worker(
                    self._cmd_aggregate_route(),
                    name="aggregate_route",
                    exclusive=True,
                )
            return

        if name == "aggregate_route":
            self._log_write(result)
            self._clear_activity()
            self._set_busy(False)
            return

        if name == "view":
            self._view_content = result
            self._view_title = f"View: {self._view_arg}"
            self._view_read_only = True
            self._note_slug = ""
            self._note_filename = ""
            self._clear_activity()
            self._set_busy(False)
            if self._editor_mode == "side":
                self._open_side(result, self._view_title, read_only=True)
            else:
                self._open_full(result, self._view_title, read_only=True)
            return

        if name == "edit":
            self._view_content = result
            self._view_title = f"Edit: {self._view_arg}"
            self._view_read_only = False
            self._note_slug = ""
            self._note_filename = ""
            self._clear_activity()
            self._set_busy(False)
            if self._editor_mode == "side":
                self._open_side(result, self._view_title, read_only=False)
            else:
                self._open_full(result, self._view_title, read_only=False)
            return

        if name == "note_new":
            self._clear_activity()
            self._set_busy(False)
            try:
                data = json.loads(result)
                slug = data["slug"]
                filename = data["filename"]
                content = data["content"]
            except (json.JSONDecodeError, KeyError, TypeError):
                # Not JSON — just a plain message (error, "usage", etc.)
                self._log_write_plain(result)
                return
            self._view_content = content
            self._view_title = f"Note: {filename}"
            self._view_read_only = False
            self._note_slug = slug
            self._note_filename = filename
            if self._editor_mode == "side":
                self._open_side(content, self._view_title, read_only=False)
            else:
                self._open_full(content, self._view_title, read_only=False)
            return

        if name == "edit_save" or name == "note_save":
            self._log_write(f"[green]{result}[/green]")
            self._clear_activity()
            self._set_busy(False)
            return

        if name == "dispatch":
            if result:
                self._log_write_plain(result)
            self._clear_activity()
            self._set_busy(False)
            return

    # ── editor mode switching ─────────────────────────────────────

    def _open_side(self, content: str, title: str, read_only: bool = False) -> None:
        editor = self.query_one(
            f"#side-editor-{self._agent_id}", SidePanelEditor,
        )
        editor.open(content=content, title=title, read_only=read_only)

    def _open_full(self, content: str, title: str, read_only: bool = False) -> None:
        self.request_editor(
            content=content,
            title=title,
            on_complete=self._on_editor_dismiss,
            read_only=read_only,
        )

    def _on_editor_dismiss(self, result: EditorResult) -> None:
        if result.metadata.get("switch_mode"):
            self._editor_mode = "side"
            self._open_side(
                result.content, self._view_title, read_only=self._view_read_only,
            )
            return
        if result.saved and not self._view_read_only:
            self._save_edit(result.content)

    def on_side_panel_editor_editor_saved(
        self, event: SidePanelEditor.EditorSaved,
    ) -> None:
        if not self._view_read_only:
            self._save_edit(event.content)

    def on_side_panel_editor_editor_switch_mode(
        self, event: SidePanelEditor.EditorSwitchMode,
    ) -> None:
        self._editor_mode = "full"
        self._open_full(
            event.content, self._view_title, read_only=self._view_read_only,
        )

    def _save_edit(self, content: str) -> None:
        self._set_busy(True)
        self._set_activity("Saving...")
        if self._note_slug and self._note_filename:
            self.run_worker(
                self._cmd_note_save(self._note_slug, self._note_filename, content),
                name="note_save",
                exclusive=True,
            )
        else:
            self.run_worker(
                self._cmd_edit_save(self._view_arg, content),
                name="edit_save",
                exclusive=True,
            )
