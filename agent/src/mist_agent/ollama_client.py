"""Thin wrapper around the Ollama Python client."""

from pathlib import Path

from ollama import chat, ChatResponse

MODEL_PATH = Path("data/config/model.conf")
DEFAULT_MODEL = "gemma3:1b"


def _load_model() -> str:
    """Read the model name from disk, falling back to the default."""
    try:
        name = MODEL_PATH.read_text(encoding="utf-8").strip()
        return name or DEFAULT_MODEL
    except FileNotFoundError:
        return DEFAULT_MODEL


def call_ollama(
    prompt: str,
    model: str | None = None,
    temperature: float = 0.3,
    system: str | None = None,
) -> str:
    """Send a single-turn user message to Ollama and return the text reply.

    If *system* is provided it is prepended as a system message.
    """
    if model is None:
        model = _load_model()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response: ChatResponse = chat(
        model=model,
        messages=messages,
    )
    return response["message"]["content"]
