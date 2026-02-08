"""Broker-connected science agent: registers with the broker, handles commands."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from mist_core.protocol import (
    Message,
    MSG_AGENT_REGISTER,
    MSG_AGENT_READY,
    MSG_COMMAND,
    MSG_RESPONSE,
)
from mist_core.transport import Client, DEFAULT_SOCKET_PATH

from .commands import dispatch
from .manifest import MANIFEST

log = logging.getLogger(__name__)


async def _register(client: Client) -> str:
    """Send agent.register and return the assigned agent_id."""
    reg = Message.create(MSG_AGENT_REGISTER, "mist-science", "broker", MANIFEST)
    reply = await client.request(reg, timeout=5.0)
    if reply.type != MSG_AGENT_READY:
        raise RuntimeError(f"registration failed: {reply.type} {reply.payload}")
    agent_id = reply.payload["agent_id"]
    log.info("registered as %s", agent_id)
    return agent_id


def _handle_sub_command(text: str) -> str | None:
    """Handle colon-prefixed sub-commands for widget flows.

    Returns the response text, or None if not a sub-command.
    """
    if ":" not in text:
        return None

    cmd, _, arg = text.partition(":")
    cmd = cmd.strip().lower()
    arg = arg.strip()

    if cmd == "article":
        return _handle_article_sub(arg)
    if cmd == "review":
        return _handle_review_sub(arg)
    return None


def _handle_article_sub(action: str) -> str:
    """Handle article:save, article:tag, article:pdf sub-commands."""
    sub, _, param = action.partition(" ")
    sub = sub.strip().lower()
    param = param.strip()

    if sub == "save":
        # param is JSON with paper data
        try:
            paper = json.loads(param)
        except json.JSONDecodeError:
            return "Error: invalid JSON for article:save"
        from mist_core.article_store import create_article
        article_id = create_article(
            title=paper.get("title", ""),
            authors=paper.get("authors", []),
            abstract=paper.get("abstract"),
            year=paper.get("year"),
            source_url=paper.get("source_url"),
            arxiv_id=paper.get("arxiv_id"),
            s2_id=paper.get("s2_id"),
        )
        return json.dumps({"article_id": article_id, "title": paper.get("title", "")})

    if sub == "tag":
        # param: "<article_id> <tag>"
        parts = param.split(None, 1)
        if len(parts) < 2:
            return "Error: usage article:tag <id> <tag>"
        from .commands import handle_tag
        return handle_tag(param)

    if sub == "pdf":
        from .commands import handle_pdf
        return handle_pdf(param)

    return f"Unknown article sub-command: {sub}"


def _handle_review_sub(action: str) -> str:
    """Handle review:refine and review:done sub-commands."""
    sub, _, param = action.partition(" ")
    sub = sub.strip().lower()
    param = param.strip()

    if sub == "refine":
        try:
            data = json.loads(param)
        except json.JSONDecodeError:
            return "Error: invalid JSON for review:refine"
        from .review import ReviewSession, refine_review, format_review_summary
        session = ReviewSession.from_json(json.dumps(data["session"]))
        instruction = data.get("instruction", "")
        updated = refine_review(session, instruction, use_llm=True)
        summary = format_review_summary(updated)
        return json.dumps({
            "type": "review",
            "session": json.loads(updated.to_json()),
            "summary": summary,
        })

    if sub == "done":
        try:
            data = json.loads(param)
        except json.JSONDecodeError:
            return "Error: invalid JSON for review:done"
        from .review import ReviewSession, finish_review
        session = ReviewSession.from_json(json.dumps(data["session"]))
        filename, message = finish_review(session)
        return json.dumps({
            "type": "review_done",
            "filename": filename,
            "message": message,
        })

    return f"Unknown review sub-command: {sub}"


async def _handle_message(msg: Message, agent_id: str, client: Client) -> None:
    """Process a single incoming command and send the response."""
    text = msg.payload.get("text", "").strip()
    if not text:
        reply = Message.reply(msg, agent_id, MSG_RESPONSE, {"text": ""})
        await client.send(reply)
        return

    # Try sub-commands first
    result = _handle_sub_command(text)
    if result is None:
        # Normal command dispatch
        result = await asyncio.to_thread(dispatch, text)

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
    """CLI entry point for mist-science."""
    parser = argparse.ArgumentParser(description="MIST science assistant agent")
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
