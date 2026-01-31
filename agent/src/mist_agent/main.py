"""REPL entry point for the MIST agent."""

from .commands import dispatch


def repl() -> None:
    """Run the interactive read-eval-print loop."""
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


if __name__ == "__main__":
    repl()
