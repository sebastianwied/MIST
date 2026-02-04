"""Tests for LLMService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mist_core.protocol import Message, MSG_SERVICE_REQUEST, MSG_SERVICE_RESPONSE, MSG_SERVICE_ERROR
from mist_core.transport import Connection

from mist_broker.llm_service import LLMService


@pytest.fixture
def mock_conn():
    conn = MagicMock(spec=Connection)
    conn.send = AsyncMock()
    return conn


@pytest.fixture
def llm():
    return LLMService()


def _llm_msg(action: str, params: dict | None = None) -> Message:
    return Message.create(
        MSG_SERVICE_REQUEST, "test", "broker",
        {"service": "llm", "action": action, "params": params or {}},
    )


def _get_reply(mock_conn) -> Message:
    assert mock_conn.send.called
    return mock_conn.send.call_args[0][0]


class TestChat:
    @patch("mist_broker.llm_service.call_ollama")
    async def test_successful_chat(self, mock_ollama, llm, mock_conn):
        mock_ollama.return_value = "Hello from LLM"
        msg = _llm_msg("chat", {"prompt": "hi", "model": "test-model"})
        await llm.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_RESPONSE
        assert reply.payload["result"] == "Hello from LLM"
        mock_ollama.assert_called_once_with(prompt="hi", model="test-model")

    @patch("mist_broker.llm_service.call_ollama")
    async def test_chat_with_system(self, mock_ollama, llm, mock_conn):
        mock_ollama.return_value = "OK"
        msg = _llm_msg("chat", {
            "prompt": "hi",
            "system": "You are helpful.",
            "temperature": 0.5,
        })
        await llm.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_RESPONSE
        mock_ollama.assert_called_once_with(
            prompt="hi", system="You are helpful.", temperature=0.5,
        )

    @patch("mist_broker.llm_service.call_ollama")
    async def test_exception_returns_error(self, mock_ollama, llm, mock_conn):
        mock_ollama.side_effect = RuntimeError("ollama down")
        msg = _llm_msg("chat", {"prompt": "hi"})
        await llm.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_ERROR
        assert "ollama down" in reply.payload["error"]


class TestUnknownAction:
    async def test_unknown_action(self, llm, mock_conn):
        msg = _llm_msg("stream")
        await llm.handle(msg, mock_conn)
        reply = _get_reply(mock_conn)
        assert reply.type == MSG_SERVICE_ERROR
        assert "unknown llm action" in reply.payload["error"]
