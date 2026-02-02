"""Thin wrapper around the Ollama Python client."""

from pathlib import Path

from ollama import chat, ChatResponse

MODEL_PATH = Path("data/config/model.conf")
DEFAULT_MODEL = "gemma3:1b"


def _load_model_conf() -> str:
    """Read the model name from model.conf, returning empty string if missing."""
    try:
        return MODEL_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def load_model() -> str:
    """Return the resolved default model name (for display / status)."""
    from .settings import get_model
    return get_model()


def call_ollama(
    prompt: str,
    model: str | None = None,
    command: str | None = None,
    temperature: float = 0.3,
    system: str | None = None,
) -> str:
    """Send a single-turn user message to Ollama and return the text reply.

    If *model* is provided it is used directly.  Otherwise the model is
    resolved via ``get_model(command)`` (settings → model.conf → default).
    If *system* is provided it is prepended as a system message.
    """
    if model is None:
        from .settings import get_model
        model = get_model(command)
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response: ChatResponse = chat(
        model=model,
        messages=messages,
    )
    return response["message"]["content"]
