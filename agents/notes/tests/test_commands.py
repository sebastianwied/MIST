"""Tests for notes agent command dispatch with mocked broker."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mist_client.protocol import (
    Message,
    MSG_COMMAND,
    MSG_RESPONSE,
    RESP_TEXT,
    RESP_LIST,
    RESP_ERROR,
    RESP_PROGRESS,
)

from notes_agent.commands import dispatch


class FakeBrokerClient:
    """Minimal mock of BrokerClient for testing command dispatch."""

    def __init__(self):
        self.sent: list[Message] = []
        self.agent_id = "notes-0"
        self._writer = None  # Prevent AttributeError

    async def _send(self, msg):
        self.sent.append(msg)

    # Storage mocks
    async def save_raw_input(self, text, source="terminal"):
        return True

    async def parse_buffer(self):
        return []

    async def clear_buffer(self):
        return True

    async def load_topic_index(self):
        return []

    async def add_topic(self, name, slug):
        return {"id": 1, "name": name, "slug": slug}

    async def find_topic(self, identifier):
        return None

    async def load_topic_buffer(self, slug):
        return []

    async def append_to_topic_buffer(self, slug, entries):
        return True

    async def load_topic_synthesis(self, slug):
        return ""

    async def save_topic_synthesis(self, slug, content):
        return True

    async def get_last_sync_time(self):
        return None

    async def set_last_sync_time(self, ts):
        return True

    async def get_last_aggregate_time(self):
        return None

    async def set_last_aggregate_time(self, ts):
        return True

    async def list_drafts(self):
        return []

    async def merge_topics(self, source, target):
        return {"entries_moved": 0}

    async def llm_chat(self, prompt, **kwargs):
        return "mock LLM response"

    async def _service_request(self, service, action, params=None):
        return True

    # Response methods
    async def respond_text(self, original, text, format="plain"):
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_TEXT, "content": {"text": text, "format": format}},
        )
        self.sent.append(reply)

    async def respond_list(self, original, items, title=""):
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_LIST, "content": {"items": items, "title": title}},
        )
        self.sent.append(reply)

    async def respond_error(self, original, message, code=""):
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_ERROR, "content": {"message": message, "code": code}},
        )
        self.sent.append(reply)

    async def respond_progress(self, original, message, percent=None):
        reply = Message.reply(
            original, self.agent_id, MSG_RESPONSE,
            {"type": RESP_PROGRESS, "content": {"message": message, "percent": percent}},
        )
        self.sent.append(reply)


def _cmd(command: str, text: str = "", args: dict | None = None) -> Message:
    payload: dict = {"command": command}
    if text:
        payload["text"] = text
    if args:
        payload["args"] = args
    return Message.create(MSG_COMMAND, "ui", "notes-0", payload)


@pytest.fixture
def client():
    return FakeBrokerClient()


class TestNoteCommand:
    async def test_note_saves(self, client):
        msg = _cmd("note", args={"text": "hello world"})
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert len(responses) == 1
        assert "Noted" in responses[0].payload["content"]["text"]

    async def test_note_requires_text(self, client):
        msg = _cmd("note")
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert responses[0].payload["type"] == RESP_ERROR


class TestNotesCommand:
    async def test_notes_empty(self, client):
        msg = _cmd("notes")
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert "No notes" in responses[0].payload["content"]["text"]


class TestRecallCommand:
    async def test_recall_requires_query(self, client):
        msg = _cmd("recall")
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert responses[0].payload["type"] == RESP_ERROR

    async def test_recall_no_entries(self, client):
        msg = _cmd("recall", args={"query": "test"})
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert "No entries" in responses[0].payload["content"]["text"]


class TestTopicsCommand:
    async def test_topics_empty(self, client):
        msg = _cmd("topics")
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert "No topics" in responses[0].payload["content"]["text"]


class TestDraftsCommand:
    async def test_drafts_empty(self, client):
        msg = _cmd("drafts")
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert "No draft" in responses[0].payload["content"]["text"]


class TestTopicAdd:
    async def test_topic_add(self, client):
        msg = _cmd("topic", args={"action": "add", "name": "Science"})
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert "Created" in responses[0].payload["content"]["text"]

    async def test_topic_add_from_text(self, client):
        msg = _cmd("topic", text="add Science")
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert "Created" in responses[0].payload["content"]["text"]


class TestAggregateCommand:
    async def test_aggregate_empty(self, client):
        msg = _cmd("aggregate")
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        text_responses = [r for r in responses if r.payload["type"] == RESP_TEXT]
        assert any("No entries" in r.payload["content"]["text"] for r in text_responses)


class TestSyncCommand:
    async def test_sync_no_topics(self, client):
        msg = _cmd("sync")
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        text_responses = [r for r in responses if r.payload["type"] == RESP_TEXT]
        assert any("No topics" in r.payload["content"]["text"] for r in text_responses)


class TestUnknownCommand:
    async def test_unknown(self, client):
        msg = _cmd("foobar")
        await dispatch(client, msg)
        responses = [m for m in client.sent if m.type == MSG_RESPONSE]
        assert responses[0].payload["type"] == RESP_ERROR
