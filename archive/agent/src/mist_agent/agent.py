"""Broker-connected MIST agent: registers with the broker, handles commands."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from io import StringIO
from pathlib import Path

from mist_core.protocol import (
    Message,
    MSG_AGENT_REGISTER,
    MSG_AGENT_READY,
    MSG_COMMAND,
    MSG_RESPONSE,
)
from mist_core.storage import load_topic_index, parse_rawlog
from mist_core.transport import Client, DEFAULT_SOCKET_PATH

from .aggregate import classify_entries, route_entries
from .commands import dispatch
from .manifest import MANIFEST
from .persona import load_persona, save_persona
from .persona_command import _generate_draft
from .view_command import save_edit

from mist_core.storage import save_draft_note, save_topic_note

log = logging.getLogger(__name__)


async def _register(client: Client) -> str:
    """Send agent.register and return the assigned agent_id."""
    reg = Message.create(MSG_AGENT_REGISTER, "mist-agent", "broker", MANIFEST)
    reply = await client.request(reg, timeout=5.0)
    if reply.type != MSG_AGENT_READY:
        raise RuntimeError(f"registration failed: {reply.type} {reply.payload}")
    agent_id = reply.payload["agent_id"]
    log.info("registered as %s", agent_id)
    return agent_id


def _collect_output(line: str, source: str) -> str:
    """Run dispatch() and capture all output into a single string."""
    buf = StringIO()

    def writer(text: str = "", **_kw) -> None:
        buf.write(str(text))
        buf.write("\n")

    result = dispatch(line, source=source, output=writer)
    captured = buf.getvalue().rstrip("\n")

    # dispatch() returns a string for free-text, None for commands
    if result is not None:
        if captured:
            return f"{captured}\n{result}"
        return result
    return captured


def _handle_sub_command(text: str) -> str | None:
    """Handle colon-prefixed sub-commands for multi-step widget flows.

    Returns the response text, or None if the text is not a sub-command.
    """
    if ":" not in text:
        return None

    cmd, _, arg = text.partition(":")
    cmd = cmd.strip().lower()
    arg = arg.strip()

    if cmd == "persona":
        return _handle_persona_sub(arg)
    if cmd == "aggregate":
        return _handle_aggregate_sub(arg)
    if cmd == "edit":
        return _handle_edit_sub(arg)
    if cmd == "note":
        return _handle_note_sub(arg)
    return None


def _handle_persona_sub(action: str) -> str:
    """Handle persona:get / persona:draft / persona:save sub-commands."""
    sub, _, param = action.partition(" ")
    sub = sub.strip().lower()
    param = param.strip()

    if sub == "get":
        return load_persona()
    if sub == "draft":
        current = load_persona()
        return _generate_draft(current, param)
    if sub == "save":
        save_persona(param)
        return "Persona updated and saved."
    return f"Unknown persona sub-command: {sub}"


def _handle_edit_sub(action: str) -> str:
    """Handle edit:save sub-command."""
    sub, _, param = action.partition(" ")
    sub = sub.strip().lower()
    param = param.strip()

    if sub == "save":
        # param format: "<name> <content>"
        name, _, content = param.partition(" ")
        return save_edit(name.strip(), content)
    return f"Unknown edit sub-command: {sub}"


def _handle_note_sub(action: str) -> str:
    """Handle note:save sub-command."""
    sub, _, param = action.partition(" ")
    sub = sub.strip().lower()
    if sub == "save":
        # param: "<slug> <filename> <content>"
        slug, _, rest = param.strip().partition(" ")
        filename, _, content = rest.partition(" ")
        if slug.strip() == "__draft__":
            save_draft_note(filename.strip(), content)
        else:
            save_topic_note(slug.strip(), filename.strip(), content)
        return f"Saved {filename.strip()}."
    return f"Unknown note sub-command: {sub}"


def _handle_aggregate_sub(action: str) -> str:
    """Handle aggregate:classify / aggregate:route sub-commands."""
    sub, _, param = action.partition(" ")
    sub = sub.strip().lower()
    param = param.strip()

    if sub == "classify":
        entries = parse_rawlog()
        if not entries:
            return json.dumps({"entries": 0, "assignments": [], "proposals": {}})
        index = load_topic_index()
        assignments, proposed = classify_entries(entries, index)
        return json.dumps({
            "entries": len(entries),
            "assignments": assignments,
            "proposals": {name: slug for name, slug in proposed.items()},
        })

    if sub == "route":
        try:
            data = json.loads(param)
        except json.JSONDecodeError:
            return "Error: invalid JSON for aggregate:route"
        entries = parse_rawlog()
        if not entries:
            return "No entries to route."
        index = load_topic_index()
        confirmed = data.get("confirmed", {})
        skipped = set(data.get("skipped", []))
        assignments = data.get("assignments", [])
        routed, new_topics = route_entries(
            entries, assignments, confirmed, skipped, index,
        )
        return f"Aggregated {routed} entries ({new_topics} new topics)."

    return f"Unknown aggregate sub-command: {sub}"


async def _handle_message(msg: Message, agent_id: str, client: Client) -> None:
    """Process a single incoming command and send the response."""
    text = msg.payload.get("text", "").strip()
    if not text:
        reply = Message.reply(msg, agent_id, MSG_RESPONSE, {"text": ""})
        await client.send(reply)
        return

    # Try sub-commands first (persona:get, aggregate:classify, etc.)
    result = _handle_sub_command(text)
    if result is None:
        # Fall through to normal dispatch
        result = await asyncio.to_thread(_collect_output, text, "broker")

    reply = Message.reply(msg, agent_id, MSG_RESPONSE, {"text": result})
    await client.send(reply)


async def run(socket_path: Path | str = DEFAULT_SOCKET_PATH) -> None:
    """Connect to the broker, register, and process commands until cancelled."""
    client = Client(path=socket_path)
    await client.connect()
    log.info("connected to broker at %s", socket_path)

    agent_id = await _register(client)

    try:
        async for msg in client:
            if msg.type == MSG_COMMAND:
                await _handle_message(msg, agent_id, client)
            else:
                log.debug("ignoring message type: %s", msg.type)
    except asyncio.CancelledError:
        log.info("agent shutting down")
    finally:
        client.close()
        await client.wait_closed()


def main() -> None:
    """CLI entry point for mist-agent."""
    parser = argparse.ArgumentParser(description="MIST broker-connected agent")
    parser.add_argument(
        "--socket",
        type=Path,
        default=DEFAULT_SOCKET_PATH,
        help="broker socket path",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    try:
        asyncio.run(run(args.socket))
    except KeyboardInterrupt:
        pass
