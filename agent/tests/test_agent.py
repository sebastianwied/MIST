"""Tests for the broker-connected MIST agent."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from mist_core.protocol import (
    Message,
    MSG_AGENT_LIST,
    MSG_AGENT_CATALOG,
    MSG_AGENT_READY,
    MSG_AGENT_REGISTER,
    MSG_COMMAND,
    MSG_RESPONSE,
)
from mist_core.transport import Client

from mist_agent.agent import _register, _collect_output, _handle_sub_command
from mist_agent.manifest import MANIFEST


# ── Unit tests (no broker) ──────────────────────────────────────────


class TestCollectOutput:
    def test_bare_command_captures_output(self):
        result = _collect_output("help", source="test")
        assert "Commands:" in result

    def test_free_text_returns_response(self):
        with patch("mist_agent.commands.handle_text", return_value="mock response"):
            result = _collect_output("hello world", source="test")
        assert result == "mock response"


class TestSubCommands:
    def test_non_sub_command_returns_none(self):
        assert _handle_sub_command("help") is None
        assert _handle_sub_command("note test") is None

    def test_persona_get(self, tmp_path, monkeypatch):
        persona_path = tmp_path / "persona.md"
        persona_path.write_text("test persona\n")
        monkeypatch.setattr("mist_agent.agent.load_persona", lambda: "test persona")
        result = _handle_sub_command("persona:get")
        assert result == "test persona"

    def test_persona_draft(self):
        with patch("mist_agent.agent._generate_draft", return_value="new draft"):
            with patch("mist_agent.agent.load_persona", return_value="current"):
                result = _handle_sub_command("persona:draft make it friendlier")
        assert result == "new draft"

    def test_persona_save(self, tmp_path, monkeypatch):
        saved = {}

        def mock_save(text):
            saved["text"] = text

        monkeypatch.setattr("mist_agent.agent.save_persona", mock_save)
        result = _handle_sub_command("persona:save new persona text")
        assert "saved" in result.lower()
        assert saved["text"] == "new persona text"

    def test_aggregate_classify_no_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mist_agent.agent.parse_rawlog", lambda: [])
        result = _handle_sub_command("aggregate:classify")
        data = json.loads(result)
        assert data["entries"] == 0

    def test_aggregate_classify_with_entries(self, monkeypatch):
        from mist_core.storage import RawLogEntry

        entries = [RawLogEntry(time="2024-01-01T00:00:00", source="test", text="hello")]
        monkeypatch.setattr("mist_agent.agent.parse_rawlog", lambda: entries)
        monkeypatch.setattr("mist_agent.agent.load_topic_index", lambda: [])

        mock_assignments = [{"index": 0, "topic_slug": "general", "new_topic": "General"}]
        monkeypatch.setattr(
            "mist_agent.agent.classify_entries",
            lambda e, i: (mock_assignments, {"General": "general"}),
        )

        result = _handle_sub_command("aggregate:classify")
        data = json.loads(result)
        assert data["entries"] == 1
        assert len(data["assignments"]) == 1
        assert "General" in data["proposals"]

    def test_unknown_sub_command(self):
        result = _handle_sub_command("persona:unknown")
        assert "Unknown" in result


# ── Integration tests (with broker) ─────────────────────────────────


class TestAgentIntegration:
    async def test_agent_registers_and_appears_in_catalog(self, running_broker):
        _, socket_path = running_broker

        # Agent connects and registers
        agent = Client(path=socket_path)
        await agent.connect()
        try:
            reg_msg = Message.create(
                MSG_AGENT_REGISTER, "mist-agent", "broker", MANIFEST,
            )
            reply = await agent.request(reg_msg, timeout=5.0)
            assert reply.type == MSG_AGENT_READY
            agent_id = reply.payload["agent_id"]
            assert agent_id == "mist-0"

            # Check catalog via a separate client
            catalog_client = Client(path=socket_path)
            await catalog_client.connect()
            try:
                list_msg = Message.create(MSG_AGENT_LIST, "test", "broker")
                cat_reply = await catalog_client.request(list_msg, timeout=5.0)
                assert cat_reply.type == MSG_AGENT_CATALOG
                agents = cat_reply.payload["agents"]
                assert len(agents) == 1
                assert agents[0]["name"] == "mist"
                assert agents[0]["widgets"] == MANIFEST["widgets"]
            finally:
                catalog_client.close()
                await catalog_client.wait_closed()
        finally:
            agent.close()
            await agent.wait_closed()

    async def test_agent_handles_help_command(self, running_broker):
        _, socket_path = running_broker

        # Register agent
        agent = Client(path=socket_path)
        await agent.connect()
        reg_reply = await agent.request(
            Message.create(MSG_AGENT_REGISTER, "agent", "broker", MANIFEST),
            timeout=5.0,
        )
        agent_id = reg_reply.payload["agent_id"]

        # Start an echo-style loop for our agent
        async def _agent_loop():
            try:
                async for msg in agent:
                    if msg.type == MSG_COMMAND:
                        text = msg.payload.get("text", "")
                        result = _collect_output(text, "broker")
                        resp = Message.reply(
                            msg, agent_id, MSG_RESPONSE, {"text": result},
                        )
                        await agent.send(resp)
            except asyncio.CancelledError:
                pass

        loop_task = asyncio.create_task(_agent_loop())

        # Widget sends "help" command
        widget = Client(path=socket_path)
        await widget.connect()
        try:
            cmd = Message.create(
                MSG_COMMAND, "widget", agent_id, {"text": "help"},
            )
            await widget.send(cmd)
            reply = await asyncio.wait_for(widget.recv(), timeout=5.0)
            assert reply is not None
            assert reply.type == MSG_RESPONSE
            assert "Commands:" in reply.payload["text"]
        finally:
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
            widget.close()
            agent.close()
            await widget.wait_closed()
            await agent.wait_closed()

    async def test_agent_handles_persona_get(self, running_broker, tmp_path, monkeypatch):
        _, socket_path = running_broker

        # Patch persona path
        persona_path = tmp_path / "persona.md"
        persona_path.write_text("test persona content\n")
        monkeypatch.setattr("mist_agent.persona.PERSONA_PATH", persona_path)

        # Register agent
        agent = Client(path=socket_path)
        await agent.connect()
        reg_reply = await agent.request(
            Message.create(MSG_AGENT_REGISTER, "agent", "broker", MANIFEST),
            timeout=5.0,
        )
        agent_id = reg_reply.payload["agent_id"]

        async def _agent_loop():
            try:
                async for msg in agent:
                    if msg.type == MSG_COMMAND:
                        text = msg.payload.get("text", "")
                        result = _handle_sub_command(text)
                        if result is None:
                            result = _collect_output(text, "broker")
                        resp = Message.reply(
                            msg, agent_id, MSG_RESPONSE, {"text": result},
                        )
                        await agent.send(resp)
            except asyncio.CancelledError:
                pass

        loop_task = asyncio.create_task(_agent_loop())

        widget = Client(path=socket_path)
        await widget.connect()
        try:
            cmd = Message.create(
                MSG_COMMAND, "widget", agent_id, {"text": "persona:get"},
            )
            await widget.send(cmd)
            reply = await asyncio.wait_for(widget.recv(), timeout=5.0)
            assert reply is not None
            assert reply.type == MSG_RESPONSE
            assert "test persona content" in reply.payload["text"]
        finally:
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
            widget.close()
            agent.close()
            await widget.wait_closed()
            await agent.wait_closed()

    async def test_agent_handles_aggregate_classify_empty(
        self, running_broker, monkeypatch,
    ):
        _, socket_path = running_broker
        monkeypatch.setattr("mist_agent.agent.parse_rawlog", lambda: [])

        agent = Client(path=socket_path)
        await agent.connect()
        reg_reply = await agent.request(
            Message.create(MSG_AGENT_REGISTER, "agent", "broker", MANIFEST),
            timeout=5.0,
        )
        agent_id = reg_reply.payload["agent_id"]

        async def _agent_loop():
            try:
                async for msg in agent:
                    if msg.type == MSG_COMMAND:
                        text = msg.payload.get("text", "")
                        result = _handle_sub_command(text)
                        if result is None:
                            result = _collect_output(text, "broker")
                        resp = Message.reply(
                            msg, agent_id, MSG_RESPONSE, {"text": result},
                        )
                        await agent.send(resp)
            except asyncio.CancelledError:
                pass

        loop_task = asyncio.create_task(_agent_loop())

        widget = Client(path=socket_path)
        await widget.connect()
        try:
            cmd = Message.create(
                MSG_COMMAND, "widget", agent_id,
                {"text": "aggregate:classify"},
            )
            await widget.send(cmd)
            reply = await asyncio.wait_for(widget.recv(), timeout=5.0)
            assert reply is not None
            data = json.loads(reply.payload["text"])
            assert data["entries"] == 0
        finally:
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
            widget.close()
            agent.close()
            await widget.wait_closed()
            await agent.wait_closed()
