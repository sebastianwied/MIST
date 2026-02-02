"""Textual TUI for the MIST agent."""

from enum import Enum, auto
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Input, Markdown, RichLog, Static, TextArea
from textual.worker import Worker, WorkerState

from .aggregate import classify_entries, route_entries
from .commands import dispatch
from .event_command import handle_event_list
from .ollama_client import load_model
from .persona import load_persona, save_persona
from .persona_command import _generate_draft
from .storage import load_topic_about, load_topic_files, load_topic_index, parse_rawlog
from .task_command import handle_task_list
from .view_command import EDITABLE_FILES, VIEWABLE_FILES, _VIRTUAL_KEYS, _all_viewable_keys

BANNER = """\
    /\\
   /  \\    ███╗   ███╗ ██╗ ███████╗ ████████╗
  / ◆  \\   ████╗ ████║ ██║ ██╔════╝ ╚══██╔══╝
 /      \\  ██╔████╔██║ ██║ ███████╗    ██║
 \\      /  ██║╚██╔╝██║ ██║ ╚════██║    ██║
  \\    /   ██║ ╚═╝ ██║ ██║ ███████║    ██║
   \\  /    ╚═╝     ╚═╝ ╚═╝ ╚══════╝    ╚═╝
    \\/\
"""


class InputMode(Enum):
    NORMAL = auto()
    PERSONA_EDIT = auto()
    PERSONA_CONFIRM = auto()
    AGGREGATE_CONFIRM = auto()


class MistApp(App):
    """A Textual TUI for the MIST reflective AI companion."""

    CSS_PATH = "mist.tcss"
    TITLE = "MIST"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+s", "save_edit", "Save", show=False),
        Binding("escape", "cancel_edit", "Cancel", show=False),
        Binding("f2", "toggle_viewer", "Toggle viewer"),
        Binding("f3", "shrink_viewer", "Shrink panel"),
        Binding("f4", "grow_viewer", "Grow panel"),
    ]

    _PANEL_WIDTHS: list[int] = [30, 40, 50, 60]

    def __init__(self) -> None:
        super().__init__()
        self._input_mode = InputMode.NORMAL
        self._persona_draft: str = ""
        self._persona_working: str = ""
        self._editing_key: str | None = None
        self._editing_path: Path | None = None
        # Aggregate state
        self._aggregate_entries: list = []
        self._aggregate_assignments: list = []
        self._aggregate_proposals: list[str] = []
        self._aggregate_current_idx: int = 0
        self._aggregate_confirmed: dict[str, str] = {}
        self._aggregate_skipped: set[str] = set()

    def compose(self) -> ComposeResult:
        yield Static(BANNER, id="banner")
        yield Static(self._build_status(), id="status-bar")
        with Horizontal(id="main-container"):
            yield RichLog(id="chat-log", markup=True, highlight=True, wrap=True)
            with VerticalScroll(id="file-viewer"):
                yield Markdown("", id="file-viewer-md")
                yield TextArea("", id="file-editor")
        yield Static("", id="activity")
        yield Input(placeholder="type a message or command", id="command-input")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#command-input", Input).focus()

    # ── status bar ──────────────────────────────────────────────

    def _build_status(self) -> str:
        model = load_model()
        persona = load_persona()
        preview = persona.replace("\n", " ")[:60]
        return f"Model: {model}  |  Persona: {preview}"

    def _refresh_status(self) -> None:
        self.query_one("#status-bar", Static).update(self._build_status())

    # ── activity indicator ────────────────────────────────────────

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

    def _set_activity(self, msg: str) -> None:
        self.query_one("#activity", Static).update(f"  {msg}")

    def _clear_activity(self) -> None:
        self.query_one("#activity", Static).update("")

    # ── file viewer ─────────────────────────────────────────────

    def action_toggle_viewer(self) -> None:
        panel = self.query_one("#file-viewer", VerticalScroll)
        panel.display = not panel.display

    def _show_file(self, name: str) -> None:
        key = name.lower()

        # Virtual key: synthesis — concatenate all topic synthesis files
        if key == "synthesis":
            topics = load_topic_files()
            if not topics:
                content = "*No synthesis topics yet. Run 'aggregate' then 'sync' first.*"
            else:
                content = "\n\n".join(
                    f"## {slug}\n{c}" for slug, c in topics.items()
                )
            self.query_one("#file-viewer-md", Markdown).update(content)
            self.query_one("#file-viewer", VerticalScroll).display = True
            return

        # Virtual key: topics
        if key == "topics":
            index = load_topic_index()
            if not index:
                content = "*No topics yet. Run 'aggregate' first.*"
            else:
                lines_t = ["## Topics\n"]
                for t in index:
                    about = load_topic_about(t.slug)
                    desc = f" — {about}" if about else ""
                    lines_t.append(f"- **[{t.id}]** `{t.slug}`: {t.name}{desc}")
                content = "\n".join(lines_t)
            self.query_one("#file-viewer-md", Markdown).update(content)
            self.query_one("#file-viewer", VerticalScroll).display = True
            return

        # Virtual key: tasks
        if key == "tasks":
            lines: list[str] = ["## Tasks\n"]
            handle_task_list("all", output=lambda t: lines.append(str(t)))
            self.query_one("#file-viewer-md", Markdown).update("\n".join(lines))
            self.query_one("#file-viewer", VerticalScroll).display = True
            return

        # Virtual key: events
        if key == "events":
            lines_ev: list[str] = ["## Events\n"]
            handle_event_list("30", output=lambda t: lines_ev.append(str(t)))
            self.query_one("#file-viewer-md", Markdown).update("\n".join(lines_ev))
            self.query_one("#file-viewer", VerticalScroll).display = True
            return

        path = VIEWABLE_FILES.get(key)
        if path is None:
            self._chat_write(
                f"Unknown file '{name}'. Available: {', '.join(_all_viewable_keys())}"
            )
            return
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            content = f"*{path} not found.*"
        self.query_one("#file-viewer-md", Markdown).update(content)
        self.query_one("#file-viewer", VerticalScroll).display = True

    # ── file editor ─────────────────────────────────────────────

    def _open_editor(self, name: str) -> None:
        key = name.lower()
        if key in _VIRTUAL_KEYS:
            self._chat_write(
                f"[yellow]'{name}' is a virtual view and cannot be edited.[/yellow]"
            )
            return
        path = VIEWABLE_FILES.get(key)
        if path is None:
            self._chat_write(
                f"Unknown file '{name}'. Editable: {', '.join(sorted(EDITABLE_FILES))}"
            )
            return
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            content = ""

        self._editing_key = key
        self._editing_path = path

        editor = self.query_one("#file-editor", TextArea)
        editor.load_text(content)
        self.query_one("#file-viewer-md", Markdown).display = False
        editor.display = True
        self.query_one("#file-viewer", VerticalScroll).display = True
        editor.focus()
        self._chat_write(f"[dim]Editing {key} — Ctrl+S to save, Escape to cancel.[/dim]")

    def action_save_edit(self) -> None:
        if self._editing_path is None:
            return
        editor = self.query_one("#file-editor", TextArea)
        self._editing_path.parent.mkdir(parents=True, exist_ok=True)
        self._editing_path.write_text(editor.text, encoding="utf-8")
        self._chat_write(f"[green]Saved {self._editing_key}.[/green]")
        self._exit_edit_mode()
        self._refresh_status()

    def action_cancel_edit(self) -> None:
        if self._editing_path is None:
            return
        self._chat_write("[yellow]Edit cancelled.[/yellow]")
        self._exit_edit_mode()

    def _exit_edit_mode(self) -> None:
        editor = self.query_one("#file-editor", TextArea)
        editor.display = False
        self.query_one("#file-viewer-md", Markdown).display = True
        self._editing_key = None
        self._editing_path = None
        self.query_one("#command-input", Input).focus()

    # ── panel resizing ─────────────────────────────────────────

    def action_grow_viewer(self) -> None:
        self._step_viewer_width(+1)

    def action_shrink_viewer(self) -> None:
        self._step_viewer_width(-1)

    def _step_viewer_width(self, direction: int) -> None:
        panel = self.query_one("#file-viewer", VerticalScroll)
        if not panel.display:
            return
        current = int(panel.styles.width.value) if panel.styles.width else 40
        widths = self._PANEL_WIDTHS
        try:
            idx = widths.index(current)
        except ValueError:
            idx = 1  # default to 40
        new_idx = max(0, min(len(widths) - 1, idx + direction))
        panel.styles.width = f"{widths[new_idx]}%"

    # ── chat output helpers ─────────────────────────────────────

    def _chat_write(self, text: str) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.write(text)

    def _chat_write_md(self, text: str) -> None:
        """Write markdown-rendered text into the chat log."""
        from rich.markdown import Markdown as RichMarkdown

        log = self.query_one("#chat-log", RichLog)
        log.write(RichMarkdown(text))

    def _tui_output(self, *args: object, **_kwargs: object) -> None:
        """Writer callback for dispatch — thread-safe."""
        text = " ".join(str(a) for a in args)
        self.call_from_thread(self._chat_write, text)

    # ── input handling ──────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        event.input.clear()
        if not line:
            return

        # ── persona state machine ──────────────────────────────
        if self._input_mode == InputMode.PERSONA_EDIT:
            if line.lower() == "done":
                self._input_mode = InputMode.NORMAL
                self._chat_write("[dim]Persona editing cancelled.[/dim]")
                return
            self._chat_write(f"[cyan]persona>[/cyan] {line}")
            self._persona_working_input = line
            self._set_input_busy(True)
            self._set_activity("Generating persona...")
            self.run_worker(
                self._generate_persona_draft(line),
                name="persona_draft",
                thread=True,
                exclusive=True,
            )
            return

        if self._input_mode == InputMode.PERSONA_CONFIRM:
            choice = line.lower()
            if choice == "yes":
                save_persona(self._persona_draft)
                self._chat_write("[green]Persona updated and saved.[/green]")
                self._input_mode = InputMode.NORMAL
                self._refresh_status()
            elif choice == "no":
                self._chat_write("[yellow]Draft discarded.[/yellow]")
                self._input_mode = InputMode.PERSONA_EDIT
                self._chat_write(
                    "[dim]Describe another change, or type 'done' to exit.[/dim]"
                )
            else:
                # Treat as further refinement
                self._persona_working = self._persona_draft
                self._chat_write(f"[cyan]persona>[/cyan] {line}")
                self._set_input_busy(True)
                self._set_activity("Generating persona...")
                self.run_worker(
                    self._generate_persona_draft(line),
                    name="persona_draft",
                    thread=True,
                    exclusive=True,
                )
            return

        # ── aggregate confirm state machine ────────────────────
        if self._input_mode == InputMode.AGGREGATE_CONFIRM:
            name = self._aggregate_proposals[self._aggregate_current_idx]
            choice = line.strip()
            if choice.lower() == "no":
                self._aggregate_skipped.add(name)
            elif choice.lower() == "yes":
                self._aggregate_confirmed[name] = "yes"
            else:
                self._aggregate_confirmed[name] = choice  # renamed

            self._aggregate_current_idx += 1
            if self._aggregate_current_idx < len(self._aggregate_proposals):
                next_name = self._aggregate_proposals[self._aggregate_current_idx]
                self._chat_write(
                    f"[dim]Create topic '{next_name}'? (yes / no / type new name)[/dim]"
                )
            else:
                self._input_mode = InputMode.NORMAL
                self._set_input_busy(True)
                self._set_activity("Routing entries...")
                self.run_worker(
                    self._run_aggregate_finish(),
                    name="aggregate_finish",
                    thread=True,
                    exclusive=True,
                )
            return

        # ── normal mode ────────────────────────────────────────
        self._chat_write(f"[bold cyan]> {line}[/bold cyan]")

        if line.lower() in ("exit", "quit"):
            self.exit()
            return

        # view command → file viewer panel
        cmd, _, arg = line.partition(" ")
        if cmd.lower() == "view":
            name = arg.strip()
            if name:
                self._show_file(name)
            else:
                self._chat_write(
                    "Viewable files: " + ", ".join(_all_viewable_keys())
                )
            return

        # edit command → open file in TextArea editor
        if cmd.lower() == "edit":
            name = arg.strip()
            if name:
                self._open_editor(name)
            else:
                self._chat_write(
                    "Editable files: " + ", ".join(sorted(EDITABLE_FILES))
                )
            return

        # aggregate → classify then confirm
        if line.strip().lower() == "aggregate":
            entries = parse_rawlog()
            if not entries:
                self._chat_write("No entries to aggregate.")
                return
            self._aggregate_entries = entries
            self._set_input_busy(True)
            self._set_activity("Aggregating...")
            self.run_worker(
                self._run_aggregate_classify(),
                name="aggregate_classify",
                thread=True,
                exclusive=True,
            )
            return

        # persona → enter edit mode
        if line.strip().lower() == "persona":
            persona_text = load_persona()
            self._persona_working = persona_text
            self._chat_write("[bold]--- Current Persona ---[/bold]")
            self._chat_write(persona_text)
            self._chat_write("[bold]-----------------------[/bold]")
            self._chat_write(
                "[dim]Describe what you'd like to change, or type 'done' to exit.[/dim]"
            )
            self._input_mode = InputMode.PERSONA_EDIT
            return

        # everything else → dispatch worker
        self._set_input_busy(True)
        label = self._ACTIVITY_LABELS.get(cmd.lower())
        if label is None and cmd.lower() not in self._NO_ACTIVITY_COMMANDS:
            label = "Thinking..."
        if label:
            self._set_activity(label)
        self.run_worker(
            self._run_dispatch(line),
            name="dispatch",
            thread=True,
            exclusive=True,
        )

    # ── workers ─────────────────────────────────────────────────

    async def _run_dispatch(self, line: str) -> str | None:
        return dispatch(line, output=self._tui_output)

    async def _generate_persona_draft(self, user_input: str) -> str:
        draft = _generate_draft(self._persona_working, user_input)
        return draft

    async def _run_aggregate_classify(self) -> tuple[list[dict], dict[str, str]]:
        index = load_topic_index()
        assignments, proposed = classify_entries(
            self._aggregate_entries, index, output=self._tui_output,
        )
        return assignments, proposed

    async def _run_aggregate_finish(self) -> tuple[int, int]:
        index = load_topic_index()
        routed, new_count = route_entries(
            self._aggregate_entries,
            self._aggregate_assignments,
            self._aggregate_confirmed,
            self._aggregate_skipped,
            index,
        )
        return routed, new_count

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state != WorkerState.SUCCESS:
            if event.state in (WorkerState.ERROR, WorkerState.CANCELLED):
                self._clear_activity()
                self._set_input_busy(False)
            return

        result = event.worker.result

        if event.worker.name == "persona_draft":
            self._persona_draft = result
            self._chat_write("[bold]--- Proposed Persona ---[/bold]")
            self._chat_write(result)
            self._chat_write("[bold]------------------------[/bold]")
            self._chat_write(
                "[dim]Apply this persona? (yes / no / describe more changes)[/dim]"
            )
            self._input_mode = InputMode.PERSONA_CONFIRM
            self._clear_activity()
            self._set_input_busy(False)
            return

        if event.worker.name == "aggregate_classify":
            assignments, proposed = result
            self._aggregate_assignments = assignments
            if not assignments:
                self._chat_write("Could not parse LLM classification. Try again.")
                self._clear_activity()
                self._set_input_busy(False)
                return
            self._aggregate_proposals = list(proposed.keys())
            self._aggregate_current_idx = 0
            self._aggregate_confirmed = {}
            self._aggregate_skipped = set()
            if self._aggregate_proposals:
                self._clear_activity()
                self._set_input_busy(False)
                self._input_mode = InputMode.AGGREGATE_CONFIRM
                name = self._aggregate_proposals[0]
                self._chat_write(
                    f"[dim]Create topic '{name}'? (yes / no / type new name)[/dim]"
                )
            else:
                # No new topics — go straight to routing
                self._set_activity("Routing entries...")
                self.run_worker(
                    self._run_aggregate_finish(),
                    name="aggregate_finish",
                    thread=True,
                    exclusive=True,
                )
            return

        if event.worker.name == "aggregate_finish":
            routed, new_count = result
            total_topics = len(load_topic_index())
            self._chat_write(
                f"Aggregated {routed} entries across {total_topics} topics ({new_count} new)."
            )
            self._clear_activity()
            self._set_input_busy(False)
            return

        if event.worker.name == "dispatch":
            if result is not None:
                self._chat_write_md(result)
            self._clear_activity()
            self._set_input_busy(False)
            self._refresh_status()

    # ── helpers ─────────────────────────────────────────────────

    def _set_input_busy(self, busy: bool) -> None:
        inp = self.query_one("#command-input", Input)
        inp.disabled = busy
        if not busy:
            inp.focus()
