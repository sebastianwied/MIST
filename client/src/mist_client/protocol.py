"""MIST message protocol v2: types, envelope, and serialization.

Vendored copy — identical to mist_core.protocol. No import relationship.
Keep in sync manually when protocol changes.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Message type constants ──────────────────────────────────────────

# Lifecycle
MSG_AGENT_REGISTER = "agent.register"
MSG_AGENT_READY = "agent.ready"
MSG_AGENT_DISCONNECT = "agent.disconnect"
MSG_AGENT_LIST = "agent.list"
MSG_AGENT_CATALOG = "agent.catalog"

# Commands
MSG_COMMAND = "command"
MSG_RESPONSE = "response"

# Services
MSG_SERVICE_REQUEST = "service.request"
MSG_SERVICE_RESPONSE = "service.response"
MSG_SERVICE_ERROR = "service.error"

# Inter-agent
MSG_AGENT_MESSAGE = "agent.message"
MSG_AGENT_BROADCAST = "agent.broadcast"

MSG_ERROR = "error"

# ── Response type constants ─────────────────────────────────────────

RESP_TEXT = "text"
RESP_TABLE = "table"
RESP_LIST = "list"
RESP_EDITOR = "editor"
RESP_CONFIRM = "confirm"
RESP_PROGRESS = "progress"
RESP_ERROR = "error"

# ── Errors ──────────────────────────────────────────────────────────


class ProtocolError(ValueError):
    """Raised when a message cannot be decoded."""


# ── Message envelope ────────────────────────────────────────────────

_REQUIRED_WIRE_KEYS = {"type", "id", "from", "to", "payload"}


@dataclass(frozen=True)
class Message:
    """Immutable message envelope.

    The *sender* field maps to the ``"from"`` key on the wire (``from``
    is a Python reserved word).
    """

    type: str
    id: str
    sender: str
    to: str
    payload: dict[str, Any] = field(default_factory=dict)
    reply_to: str | None = None
    timestamp: str | None = None

    # ── Constructors ────────────────────────────────────────────────

    @classmethod
    def create(
        cls,
        type: str,
        sender: str,
        to: str,
        payload: dict[str, Any] | None = None,
        reply_to: str | None = None,
    ) -> Message:
        """Build a new message with a fresh UUID and auto-set timestamp."""
        return cls(
            type=type,
            id=uuid.uuid4().hex,
            sender=sender,
            to=to,
            payload=payload if payload is not None else {},
            reply_to=reply_to,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )

    @classmethod
    def reply(
        cls,
        original: Message,
        sender: str,
        type: str,
        payload: dict[str, Any] | None = None,
    ) -> Message:
        """Build a reply addressed to *original*'s sender."""
        return cls.create(
            type=type,
            sender=sender,
            to=original.sender,
            payload=payload,
            reply_to=original.id,
        )


# ── Serialization ───────────────────────────────────────────────────


def encode_message(msg: Message) -> str:
    """Serialize *msg* to a single JSON line (no trailing newline).

    The ``sender`` field is written as ``"from"`` on the wire.
    """
    d = asdict(msg)
    d["from"] = d.pop("sender")
    if d["reply_to"] is None:
        del d["reply_to"]
    return json.dumps(d, separators=(",", ":"))


def decode_message(line: str) -> Message:
    """Deserialize a JSON line into a `Message`.

    Raises `ProtocolError` on invalid input.
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ProtocolError("message must be a JSON object")

    missing = _REQUIRED_WIRE_KEYS - data.keys()
    if missing:
        raise ProtocolError(f"missing required keys: {sorted(missing)}")

    return Message(
        type=data["type"],
        id=data["id"],
        sender=data["from"],
        to=data["to"],
        payload=data["payload"],
        reply_to=data.get("reply_to"),
        timestamp=data.get("timestamp"),
    )
