"""Handlers for sync, resynth, and per-topic synthesis commands."""

import re

from .notes import _format_entries
from .ollama_client import call_ollama, load_deep_model
from .prompts import CONTEXT_GEN_PROMPT, TOPIC_RESYNTH_PROMPT, TOPIC_SYNC_PROMPT
from .storage import (
    find_topic,
    get_last_sync_time,
    load_topic_files,
    load_topic_index,
    load_topic_notelog,
    load_topic_synthesis,
    save_context,
    save_topic_synthesis,
    set_last_sync_time,
)
from .types import Writer


def _slugify(heading: str) -> str:
    """Lowercase, replace non-alnum with hyphens, collapse, strip."""
    slug = re.sub(r"[^a-z0-9]+", "-", heading.lower())
    return slug.strip("-")


# --- Context generation ---

def _generate_context(output: Writer = print) -> None:
    """Read all topic synthesis files and generate context.md via LLM."""
    topics = load_topic_files()
    if not topics:
        save_context("")
        return

    all_topics = "\n\n".join(
        f"## {slug}\n{content}" for slug, content in topics.items()
    )
    prompt = CONTEXT_GEN_PROMPT.format(all_topics=all_topics)
    result = call_ollama(prompt)
    save_context(result)
    output("Context updated (data/synthesis/context.md).")


# --- Sync (per-topic incremental) ---

def handle_sync(output: Writer = print) -> None:
    """Incrementally update each topic's synthesis and regenerate context."""
    output("Syncing synthesis...")

    index = load_topic_index()
    if not index:
        output("No topics yet. Run 'aggregate' first.")
        return

    high_water = get_last_sync_time()
    any_updated = False
    latest_time = high_water

    for topic in index:
        entries = load_topic_notelog(topic.slug)
        if high_water:
            entries = [e for e in entries if e.time > high_water]
        if not entries:
            continue

        current_synthesis = load_topic_synthesis(topic.slug)
        formatted = _format_entries(entries)
        prompt = TOPIC_SYNC_PROMPT.format(
            topic_name=topic.name,
            current_synthesis=current_synthesis or "(no existing synthesis)",
            new_entries=formatted,
        )
        result = call_ollama(prompt)
        save_topic_synthesis(topic.slug, result)
        output(f"  Updated: {topic.name}")
        any_updated = True

        if entries and (latest_time is None or entries[-1].time > latest_time):
            latest_time = entries[-1].time

    if not any_updated:
        output("No new entries since last sync.")
        return

    output(f"Topics updated ({len(index)} topics in data/topics/).")
    _generate_context(output=output)

    if latest_time:
        set_last_sync_time(latest_time)


# --- Resynth (per-topic full rewrite) ---

def handle_resynth(output: Writer = print) -> None:
    """Full rewrite of each topic's synthesis using the deep model."""
    deep_model = load_deep_model()
    output(f"Deep resynthesis using {deep_model}...")

    index = load_topic_index()
    if not index:
        output("No topics yet. Run 'aggregate' first.")
        return

    latest_time = None
    for topic in index:
        entries = load_topic_notelog(topic.slug)
        if not entries:
            continue

        formatted = _format_entries(entries)
        prompt = TOPIC_RESYNTH_PROMPT.format(
            topic_name=topic.name,
            all_entries=formatted,
        )
        result = call_ollama(prompt, model=deep_model)
        save_topic_synthesis(topic.slug, result)
        output(f"  Resynthesized: {topic.name}")

        if entries and (latest_time is None or entries[-1].time > latest_time):
            latest_time = entries[-1].time

    output(f"Topics rewritten ({len(index)} topics in data/topics/).")
    _generate_context(output=output)

    if latest_time:
        set_last_sync_time(latest_time)


# --- Single-topic synthesis ---

def handle_synthesis(identifier: str, output: Writer = print) -> None:
    """Resynthesize a single topic by id or slug using the deep model."""
    if not identifier:
        output("Usage: synthesis <id|slug>")
        return

    topic = find_topic(identifier)
    if topic is None:
        output(f"Topic '{identifier}' not found. Use 'view topics' to list.")
        return

    deep_model = load_deep_model()
    output(f"Resynthesizing '{topic.name}' using {deep_model}...")

    entries = load_topic_notelog(topic.slug)
    if not entries:
        output(f"No entries in topic '{topic.name}'.")
        return

    formatted = _format_entries(entries)
    prompt = TOPIC_RESYNTH_PROMPT.format(
        topic_name=topic.name,
        all_entries=formatted,
    )
    result = call_ollama(prompt, model=deep_model)
    save_topic_synthesis(topic.slug, result)
    output(f"Synthesis updated for '{topic.name}'.")

    _generate_context(output=output)
