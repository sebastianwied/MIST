"""Thin wrapper around the Ollama Python client."""

from __future__ import annotations

from ollama import chat, ChatResponse

from ..storage.settings import Settings


class OllamaClient:
    """Ollama LLM client.

    Usage:
        client = OllamaClient(settings)
        response = client.chat("Hello", command="reflect")
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def chat(
        self,
        prompt: str,
        model: str | None = None,
        command: str | None = None,
        temperature: float = 0.3,
        system: str | None = None,
    ) -> str:
        """Send a single-turn message and return the text reply.

        Model resolution: explicit *model* > settings chain via *command*.
        """
        if model is None:
            model = self._settings.get_model(command)
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response: ChatResponse = chat(
            model=model,
            messages=messages,
        )
        return response["message"]["content"]
