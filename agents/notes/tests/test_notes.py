"""Tests for note/recall/topics handlers."""

from __future__ import annotations

import pytest

from mist_client.protocol import Message, MSG_COMMAND, MSG_RESPONSE, RESP_TEXT, RESP_LIST

from notes_agent.notes import _format_entries, handle_note, handle_notes, handle_topics


class FakeClient:
    """Minimal mock client."""

    def __init__(self):
        self.sent = []
        self.agent_id = "notes-0"
        self._saved = []
        self._buffer = []

    async def save_raw_input(self, text, source="terminal"):
        self._saved.append({"text": text, "source": source})
        return True

    async def parse_buffer(self):
        return self._buffer

    async def load_topic_index(self):
        return []

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


def _cmd() -> Message:
    return Message.create(MSG_COMMAND, "ui", "notes-0", {"command": "note"})


class TestFormatEntries:
    def test_format(self):
        entries = [
            {"time": "2025-01-01T00:00:00", "source": "note", "text": "hello"},
            {"time": "2025-01-02T00:00:00", "source": "terminal", "text": "world"},
        ]
        result = _format_entries(entries)
        assert "[2025-01-01T00:00:00]" in result
        assert "(note)" in result
        assert "hello" in result


class TestHandleNote:
    async def test_saves_and_responds(self):
        client = FakeClient()
        msg = _cmd()
        await handle_note(client, msg, "test note")
        assert len(client._saved) == 1
        assert client._saved[0]["text"] == "test note"
        assert len(client.sent) == 1
        assert "Noted" in client.sent[0].payload["content"]["text"]


class TestHandleNotes:
    async def test_empty(self):
        client = FakeClient()
        msg = _cmd()
        await handle_notes(client, msg)
        assert "No notes" in client.sent[0].payload["content"]["text"]

    async def test_with_entries(self):
        client = FakeClient()
        client._buffer = [
            {"time": "2025-01-01T00:00:00", "source": "note", "text": "hello"},
            {"time": "2025-01-02T00:00:00", "source": "terminal", "text": "not a note"},
        ]
        msg = _cmd()
        await handle_notes(client, msg)
        text = client.sent[0].payload["content"]["text"]
        assert "hello" in text
        # Terminal entries should be excluded
        assert "not a note" not in text


class TestHandleTopics:
    async def test_empty(self):
        client = FakeClient()
        msg = _cmd()
        await handle_topics(client, msg)
        assert "No topics" in client.sent[0].payload["content"]["text"]
