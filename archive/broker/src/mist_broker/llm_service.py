"""LLM service: Ollama wrapper via asyncio.to_thread.

Separated from services.py because LLM calls are slow (seconds) and will
later gain queuing and streaming support.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mist_core.ollama_client import call_ollama
from mist_core.protocol import Message, MSG_SERVICE_RESPONSE, MSG_SERVICE_ERROR
from mist_core.transport import Connection

log = logging.getLogger(__name__)

BROKER_ID = "broker"


class LLMService:
    """Handle service.request messages where service == "llm"."""

    async def handle(self, msg: Message, conn: Connection) -> None:
        """Dispatch an LLM service request and send the result back."""
        payload = msg.payload
        try:
            action = payload.get("action")
            match action:
                case "chat":
                    result = await self._handle_chat(payload)
                case _:
                    raise ValueError(f"unknown llm action: {action}")
            reply = Message.reply(
                msg, BROKER_ID, MSG_SERVICE_RESPONSE, {"result": result},
            )
        except Exception as exc:
            log.exception("llm service error: %s", exc)
            reply = Message.reply(
                msg, BROKER_ID, MSG_SERVICE_ERROR, {"error": str(exc)},
            )
        await conn.send(reply)

    async def _handle_chat(self, payload: dict) -> str:
        params = payload.get("params", {})
        return await asyncio.to_thread(call_ollama, **params)
