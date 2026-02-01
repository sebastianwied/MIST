"""Textual TUI for the MIST agent."""

from enum import Enum, auto
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Footer, Input, Markdown, RichLog, Static
from textual.worker import Worker, WorkerState

from .commands import dispatch
from .event_command import handle_event_list
from .ollama_client import load_model
from .persona import load_persona, save_persona
from .persona_command import _generate_draft
from .storage import load_topic_files
from .task_command import handle_task_list
from .view_command import VIEWABLE_FILES, _VIRTUAL_KEYS, _all_viewable_keys

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


class MistApp(App):
    """A Textual TUI for the MIST reflective AI companion."""

    CSS_PATH = "mist.tcss"
    TITLE = "MIST"
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f2", "toggle_viewer", "Toggle viewer"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._input_mode = InputMode.NORMAL
        self._persona_draft: str = ""
        self._persona_working: str = ""

    def compose(self) -> ComposeResult:
        yield Static(BANNER, id="banner")
        yield Static(self._build_status(), id="status-bar")
        with Horizontal(id="main-container"):
            yield RichLog(id="chat-log", markup=True, highlight=True, wrap=True)
            with VerticalScroll(id="file-viewer"):
                yield Markdown("", id="file-viewer-md")
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

    # ── file viewer ─────────────────────────────────────────────

    def action_toggle_viewer(self) -> None:
        panel = self.query_one("#file-viewer", VerticalScroll)
        panel.display = not panel.display

    def _show_file(self, name: str) -> None:
        key = name.lower()

        # Virtual key: synthesis — concatenate all topic files
        if key == "synthesis":
            topics = load_topic_files()
            if not topics:
                content = "*No synthesis topics yet. Run 'sync' first.*"
            else:
                content = "\n\n".join(topics.values())
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
                self.run_worker(
                    self._generate_persona_draft(line),
                    name="persona_draft",
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

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state != WorkerState.SUCCESS:
            if event.state in (WorkerState.ERROR, WorkerState.CANCELLED):
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
            self._set_input_busy(False)
            return

        if event.worker.name == "dispatch":
            if result is not None:
                self._chat_write_md(result)
            self._set_input_busy(False)
            self._refresh_status()

    # ── helpers ─────────────────────────────────────────────────

    def _set_input_busy(self, busy: bool) -> None:
        inp = self.query_one("#command-input", Input)
        inp.disabled = busy
        if not busy:
            inp.focus()
