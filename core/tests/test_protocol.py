"""Tests for mist_core.protocol."""

import json
import uuid

import pytest

from mist_core.protocol import (
    Message,
    ProtocolError,
    decode_message,
    encode_message,
    MSG_COMMAND,
    MSG_RESPONSE,
    MSG_AGENT_MESSAGE,
    RESP_TEXT,
    RESP_TABLE,
)


class TestMessageCreate:
    def test_generates_valid_uuid(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b")
        assert len(msg.id) == 32
        uuid.UUID(msg.id, version=4)

    def test_default_payload_is_empty_dict(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b")
        assert msg.payload == {}

    def test_payload_preserved(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b", payload={"k": 1})
        assert msg.payload == {"k": 1}

    def test_reply_to_default_none(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b")
        assert msg.reply_to is None

    def test_timestamp_auto_set(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b")
        assert msg.timestamp is not None
        assert "T" in msg.timestamp  # ISO 8601

    def test_new_message_types_exist(self):
        # Verify v2 constants are available
        assert MSG_AGENT_MESSAGE == "agent.message"
        assert RESP_TEXT == "text"
        assert RESP_TABLE == "table"


class TestMessageReply:
    def test_fills_to_and_reply_to(self):
        orig = Message.create(MSG_COMMAND, sender="client", to="server")
        rep = Message.reply(orig, sender="server", type=MSG_RESPONSE, payload={"ok": True})
        assert rep.to == "client"
        assert rep.reply_to == orig.id
        assert rep.sender == "server"
        assert rep.type == MSG_RESPONSE
        assert rep.payload == {"ok": True}

    def test_reply_has_timestamp(self):
        orig = Message.create(MSG_COMMAND, sender="a", to="b")
        rep = Message.reply(orig, sender="b", type=MSG_RESPONSE)
        assert rep.timestamp is not None


class TestFrozen:
    def test_assignment_raises(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b")
        with pytest.raises(AttributeError):
            msg.type = "other"  # type: ignore[misc]


class TestRoundTrip:
    def test_encode_decode_preserves_equality(self):
        msg = Message.create(
            MSG_COMMAND,
            sender="cli",
            to="broker",
            payload={"text": "hello"},
            reply_to="abc123",
        )
        line = encode_message(msg)
        restored = decode_message(line)
        assert restored == msg

    def test_round_trip_without_reply_to(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b")
        restored = decode_message(encode_message(msg))
        assert restored == msg
        assert restored.reply_to is None

    def test_timestamp_survives_round_trip(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b")
        restored = decode_message(encode_message(msg))
        assert restored.timestamp == msg.timestamp


class TestWireFormat:
    def test_uses_from_not_sender(self):
        msg = Message.create(MSG_COMMAND, sender="cli", to="broker")
        wire = json.loads(encode_message(msg))
        assert "from" in wire
        assert "sender" not in wire

    def test_reply_to_omitted_when_none(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b")
        wire = json.loads(encode_message(msg))
        assert "reply_to" not in wire

    def test_timestamp_present_on_wire(self):
        msg = Message.create(MSG_COMMAND, sender="a", to="b")
        wire = json.loads(encode_message(msg))
        assert "timestamp" in wire


class TestDecodeErrors:
    def test_invalid_json(self):
        with pytest.raises(ProtocolError, match="invalid JSON"):
            decode_message("not json {{{")

    def test_non_object(self):
        with pytest.raises(ProtocolError, match="JSON object"):
            decode_message("[1, 2, 3]")

    def test_missing_required_fields(self):
        with pytest.raises(ProtocolError, match="missing required keys"):
            decode_message('{"type": "command"}')

    def test_missing_from(self):
        data = json.dumps({"type": "x", "id": "1", "to": "b", "payload": {}})
        with pytest.raises(ProtocolError, match="from"):
            decode_message(data)
