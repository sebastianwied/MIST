"""Handlers for sync, resynth, and per-topic synthesis commands."""

from __future__ import annotations

from mist_client import BrokerClient
from mist_client.protocol import Message

from .notes import _format_entries
from .prompts import TOPIC_RESYNTH_PROMPT, TOPIC_SYNC_PROMPT


async def handle_sync(client: BrokerClient, msg: Message) -> None:
    """Incrementally update each topic's synthesis with new entries."""
    await client.respond_progress(msg, "Syncing synthesis...")

    index = await client.load_topic_index()
    if not index:
        await client.respond_text(msg, "No topics yet. Run 'aggregate' first.")
        return

    high_water = await client.get_last_sync_time()
    updated_topics = []
    latest_time = high_water

    for topic in index:
        slug = topic.get("slug", "")
        name = topic.get("name", slug)

        entries = await client.load_topic_buffer(slug)
        if high_water:
            entries = [e for e in entries if e.get("time", "") > high_water]
        if not entries:
            continue

        current = await client.load_topic_synthesis(slug)
        formatted = _format_entries(entries)

        prompt = TOPIC_SYNC_PROMPT.format(
            topic_name=name,
            current_synthesis=current or "(no existing synthesis)",
            new_entries=formatted,
            notes="(no long-form notes)",
        )
        result = await client.llm_chat(prompt, command="sync")
        await client.save_topic_synthesis(slug, result)
        updated_topics.append(name)

        if entries:
            last = entries[-1].get("time", "")
            if latest_time is None or last > latest_time:
                latest_time = last

    if not updated_topics:
        await client.respond_text(msg, "No new entries since last sync.")
        return

    if latest_time:
        await client.set_last_sync_time(latest_time)

    await client.respond_text(
        msg,
        f"Updated {len(updated_topics)} topics: {', '.join(updated_topics)}",
    )


async def handle_resynth(client: BrokerClient, msg: Message) -> None:
    """Full rewrite of each topic's synthesis."""
    await client.respond_progress(msg, "Deep resynthesis...")

    index = await client.load_topic_index()
    if not index:
        await client.respond_text(msg, "No topics yet. Run 'aggregate' first.")
        return

    latest_time = None
    updated_topics = []

    for topic in index:
        slug = topic.get("slug", "")
        name = topic.get("name", slug)

        entries = await client.load_topic_buffer(slug)
        if not entries:
            continue

        formatted = _format_entries(entries)
        prompt = TOPIC_RESYNTH_PROMPT.format(
            topic_name=name,
            all_entries=formatted,
            notes="(no long-form notes)",
        )
        result = await client.llm_chat(prompt, command="resynth")
        await client.save_topic_synthesis(slug, result)
        updated_topics.append(name)

        if entries:
            last = entries[-1].get("time", "")
            if latest_time is None or last > latest_time:
                latest_time = last

    if latest_time:
        await client.set_last_sync_time(latest_time)

    await client.respond_text(
        msg,
        f"Resynthesized {len(updated_topics)} topics: {', '.join(updated_topics)}",
    )


async def handle_synthesis(
    client: BrokerClient, msg: Message, identifier: str,
) -> None:
    """Resynthesize a single topic by id or slug."""
    if not identifier:
        await client.respond_error(msg, "Usage: synthesis <id|slug>")
        return

    topic = await client.find_topic(identifier)
    if not topic:
        await client.respond_error(msg, f"Topic '{identifier}' not found.")
        return

    slug = topic.get("slug", "")
    name = topic.get("name", slug)

    entries = await client.load_topic_buffer(slug)
    if not entries:
        await client.respond_text(msg, f"No entries in topic '{name}'.")
        return

    await client.respond_progress(msg, f"Resynthesizing '{name}'...")

    formatted = _format_entries(entries)
    prompt = TOPIC_RESYNTH_PROMPT.format(
        topic_name=name,
        all_entries=formatted,
        notes="(no long-form notes)",
    )
    result = await client.llm_chat(prompt, command="synthesis")
    await client.save_topic_synthesis(slug, result)
    await client.respond_text(msg, f"Synthesis updated for '{name}'.")
