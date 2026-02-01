"""Entry points for the MIST agent."""

from .commands import dispatch


def repl() -> None:
    """Run the interactive read-eval-print loop (plain terminal fallback)."""
    while True:
        try:
            line = input("> ").strip()
            if not line:
                continue
            if line in {"exit", "quit"}:
                break

            result = dispatch(line)
            if result is not None:
                print(result)

        except KeyboardInterrupt:
            print("\nExiting.")
            break


def tui() -> None:
    """Launch the Textual TUI."""
    from .tui import MistApp

    MistApp().run()


if __name__ == "__main__":
    repl()
