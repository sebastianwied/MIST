"""Handler for free-text reflection input."""

from .ollama_client import call_ollama
from .prompts import REFLECTION_PROMPT
from .storage import save_raw_input


def handle_text(text: str, source: str = "terminal") -> str:
    """Log the input and return a reflective response from Ollama."""
    save_raw_input(text, source=source)
    prompt = REFLECTION_PROMPT.format(text=text)
    return call_ollama(prompt)
