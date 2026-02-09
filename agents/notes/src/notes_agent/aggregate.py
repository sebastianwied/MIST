"""Aggregate handler: classify buffer entries into topics and route them."""

from __future__ import annotations

import json
import re
from typing import Any

from mist_client import BrokerClient
from mist_client.protocol import Message

from .notes import _format_entries
from .prompts import AGGREGATE_ASSIGNMENT_PROMPT


def _slugify(heading: str) -> str:
    """Lowercase, replace non-alnum with hyphens, collapse, strip."""
    slug = re.sub(r"[^a-z0-9]+", "-", heading.lower())
    return slug.strip("-")


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` wrapping."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _extract_json_array(text: str) -> str | None:
    """Find the first top-level JSON array in text."""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _parse_assignments(raw: str) -> list[dict]:
    """Parse JSON assignment array from LLM output."""
    cleaned = _strip_code_fences(raw)
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    arr = _extract_json_array(raw)
    if arr:
        try:
            result = json.loads(arr)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    return []


async def handle_aggregate(client: BrokerClient, msg: Message) -> None:
    """Classify buffer entries into topics and route them."""
    entries = await client.parse_buffer()
    if not entries:
        await client.respond_text(msg, "No entries to aggregate.")
        return

    index = await client.load_topic_index()
    await client.respond_progress(msg, f"Classifying {len(entries)} entries...")

    # Build topic text for prompt
    if index:
        existing_text = "\n".join(
            f"- {t.get('slug', '')}: {t.get('name', '')}" for t in index
        )
    else:
        existing_text = "(no existing topics)"

    formatted = _format_entries(entries)
    prompt = AGGREGATE_ASSIGNMENT_PROMPT.format(
        existing_topics=existing_text,
        new_entries=formatted,
    )

    # Classify via LLM (retry up to 3 times)
    assignments = []
    for attempt in range(3):
        result = await client.llm_chat(prompt, command="aggregate")
        assignments = _parse_assignments(result)
        if assignments:
            break

    if not assignments:
        await client.respond_error(msg, "Failed to parse LLM classification output.")
        return

    # Identify proposed new topics
    existing_slugs = {t.get("slug") for t in index}
    new_topics: dict[str, str] = {}  # name -> slug
    for a in assignments:
        new_name = a.get("new_topic")
        if new_name and new_name != "__skip__":
            slug = _slugify(new_name)
            if slug and slug not in existing_slugs and new_name not in new_topics:
                new_topics[new_name] = slug

    # Create new topics (auto-accept in v2)
    for name, slug in new_topics.items():
        await client.add_topic(name, slug)

    # Refresh index after creating topics
    index = await client.load_topic_index()
    all_slugs = {t.get("slug") for t in index}

    # Route entries to topics
    topic_entries: dict[str, list[dict]] = {}
    routed_count = 0
    handled_indices: set[int] = set()

    for a in assignments:
        idx = a.get("index")
        if idx is None or idx < 0 or idx >= len(entries):
            continue

        slug = a.get("topic_slug")
        new_name = a.get("new_topic")

        if slug == "__skip__":
            handled_indices.add(idx)
            continue

        if new_name:
            target_slug = new_topics.get(new_name)
        elif slug and slug in all_slugs:
            target_slug = slug
        else:
            continue

        if not target_slug:
            continue

        if target_slug not in topic_entries:
            topic_entries[target_slug] = []
        topic_entries[target_slug].append(entries[idx])
        handled_indices.add(idx)
        routed_count += 1

    # Append entries to topic buffers
    for slug, ents in topic_entries.items():
        await client.append_to_topic_buffer(slug, ents)

    # Rewrite buffer with unhandled entries
    leftover = [entries[i] for i in range(len(entries)) if i not in handled_indices]
    if leftover:
        await client._service_request("storage", "write_buffer", {"entries": leftover})
    else:
        await client.clear_buffer()

    # Update aggregate timestamp
    if entries:
        await client.set_last_aggregate_time(entries[-1].get("time", ""))

    await client.respond_text(
        msg,
        f"Aggregated {routed_count} entries across {len(index)} topics "
        f"({len(new_topics)} new).",
    )


async def handle_topic_add(client: BrokerClient, msg: Message, name: str) -> None:
    """Manually create a new topic."""
    slug = _slugify(name)
    if not slug:
        await client.respond_error(msg, "Invalid topic name.")
        return

    existing = await client.find_topic(slug)
    if existing:
        await client.respond_text(msg, f"Topic '{existing.get('name')}' already exists.")
        return

    topic = await client.add_topic(name, slug)
    await client.respond_text(
        msg, f"Created topic [{topic.get('id')}] {topic.get('slug')}: {topic.get('name')}",
    )


async def handle_topic_merge(
    client: BrokerClient, msg: Message, source_id: str, target_id: str,
) -> None:
    """Merge source topic into target topic."""
    if not target_id:
        await client.respond_error(msg, "Usage: topic merge <source> <target>")
        return

    source = await client.find_topic(source_id)
    if not source:
        await client.respond_error(msg, f"Source topic '{source_id}' not found.")
        return

    target = await client.find_topic(target_id)
    if not target:
        await client.respond_error(msg, f"Target topic '{target_id}' not found.")
        return

    if source.get("slug") == target.get("slug"):
        await client.respond_error(msg, "Source and target are the same topic.")
        return

    result = await client.merge_topics(source["slug"], target["slug"])
    count = result.get("entries_moved", 0)
    await client.respond_text(
        msg,
        f"Merged {count} entries from '{source.get('name')}' into '{target.get('name')}'.",
    )
