"""Miscellaneous helpers: status check, model stop."""

import subprocess

from .types import Writer


def handle_status(output: Writer = print) -> None:
    """Print a brief status report (placeholder)."""
    output("status check...")


def stop_model(model: str = "gemma3:1b") -> None:
    """Ask Ollama to unload the model from memory."""
    subprocess.run(["ollama", "stop", model])
