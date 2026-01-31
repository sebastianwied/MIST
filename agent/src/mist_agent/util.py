"""Miscellaneous helpers: status check, model stop."""

import subprocess


def handle_status() -> None:
    """Print a brief status report (placeholder)."""
    print("status check...")


def stop_model(model: str = "gemma3:1b") -> None:
    """Ask Ollama to unload the model from memory."""
    subprocess.run(["ollama", "stop", model])
