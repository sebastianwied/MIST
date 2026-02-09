"""Command dispatch for the notes agent."""

from __future__ import annotations

from mist_client import BrokerClient
from mist_client.protocol import Message

from .aggregate import handle_aggregate, handle_topic_add, handle_topic_merge
from .notes import (
    handle_drafts, handle_note, handle_notes, handle_recall, handle_topics,
    handle_topic_view, handle_topic_read, handle_topic_write,
)
from .synthesis import handle_resynth, handle_sync, handle_synthesis


async def dispatch(client: BrokerClient, msg: Message) -> None:
    """Route a command message to the appropriate handler."""
    payload = msg.payload
    command = payload.get("command", "")
    args = payload.get("args", {})
    text = payload.get("text", "")

    match command:
        case "note":
            note_text = args.get("text", "") or text
            if not note_text:
                await client.respond_error(msg, "Usage: note <text>")
                return
            await handle_note(client, msg, note_text)

        case "notes":
            await handle_notes(client, msg)

        case "recall":
            query = args.get("query", "") or text
            if not query:
                await client.respond_error(msg, "Usage: recall <query>")
                return
            await handle_recall(client, msg, query)

        case "aggregate":
            await handle_aggregate(client, msg)

        case "sync":
            await handle_sync(client, msg)

        case "resynth":
            await handle_resynth(client, msg)

        case "synthesis":
            topic_id = args.get("topic", "") or text
            await handle_synthesis(client, msg, topic_id)

        case "topics":
            await handle_topics(client, msg)

        case "drafts":
            await handle_drafts(client, msg)

        case "topic":
            action = args.get("action", "")
            if not action and text:
                action, _, text = text.partition(" ")
                action = action.lower()

            if action == "add":
                name = args.get("name", "") or text
                await handle_topic_add(client, msg, name)
            elif action == "merge":
                parts = text.split(None, 1) if text else []
                source = args.get("source", "") or (parts[0] if parts else "")
                target = args.get("target", "") or (parts[1] if len(parts) > 1 else "")
                await handle_topic_merge(client, msg, source, target)
            elif action == "view":
                slug = args.get("slug", "") or text.strip()
                await handle_topic_view(client, msg, slug)
            elif action == "read":
                parts = text.strip().split(None, 1) if text else []
                slug = args.get("slug", "") or (parts[0] if parts else "")
                filename = args.get("filename", "") or (parts[1] if len(parts) > 1 else "synthesis")
                await handle_topic_read(client, msg, slug, filename)
            elif action == "write":
                slug = args.get("slug", "")
                filename = args.get("filename", "synthesis")
                content = args.get("content", "")
                await handle_topic_write(client, msg, slug, filename, content)
            else:
                await client.respond_error(
                    msg, "Usage: topic add|merge|view|read|write <args>",
                )

        case _:
            await client.respond_error(msg, f"Unknown command: {command}")
