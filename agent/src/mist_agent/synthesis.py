"""Handlers for sync and resynth commands, plus topic-document parsing."""

import re

from .notes import _format_entries
from .ollama_client import call_ollama, load_deep_model
from .profile_command import handle_profile
from .prompts import CONTEXT_GEN_PROMPT, TOPIC_RESYNTH_PROMPT, TOPIC_SYNC_PROMPT
from .storage import (
    SYNTHESIS_DIR,
    delete_topic_file,
    get_last_sync_time,
    load_topic_files,
    parse_rawlog,
    parse_rawlog_full,
    rotate_rawlog,
    save_context,
    save_topic_file,
    set_last_sync_time,
)
from .types import Writer


# --- Topic-document parsing ---

def _slugify(heading: str) -> str:
    """Lowercase, replace non-alnum with hyphens, collapse, strip."""
    slug = re.sub(r"[^a-z0-9]+", "-", heading.lower())
    return slug.strip("-")


def parse_topic_document(text: str) -> dict[str, str]:
    """Split text on '## ' boundaries, return {slug: section_content}.

    Discards any text before the first '## '.
    """
    topics: dict[str, str] = {}
    current_heading = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            # Save previous section
            if current_heading is not None:
                slug = _slugify(current_heading)
                body = "\n".join(current_lines).strip()
                if slug and body:
                    topics[slug] = f"## {current_heading}\n{body}"
            current_heading = line[3:].strip()
            current_lines = []
        elif current_heading is not None:
            current_lines.append(line)

    # Save last section
    if current_heading is not None:
        slug = _slugify(current_heading)
        body = "\n".join(current_lines).strip()
        if slug and body:
            topics[slug] = f"## {current_heading}\n{body}"

    return topics


# --- Context generation ---

def _generate_context(output: Writer = print) -> None:
    """Read all topic files and generate context.md via LLM."""
    topics = load_topic_files()
    if not topics:
        save_context("")
        return

    all_topics = "\n\n".join(topics.values())
    prompt = CONTEXT_GEN_PROMPT.format(all_topics=all_topics)
    result = call_ollama(prompt)
    save_context(result)
    output("Context updated (data/synthesis/context.md).")


# --- Sync ---

def handle_sync(output: Writer = print) -> None:
    """Incrementally update per-topic synthesis files and context."""
    output("Syncing synthesis...")

    # Phase 1: Topic update
    entries = parse_rawlog()
    if not entries:
        output("No entries to synthesize.")
        return

    high_water = get_last_sync_time()
    new_entries = entries
    if high_water:
        new_entries = [e for e in entries if e.time > high_water]

    if not new_entries:
        output("No new entries since last sync.")
        return

    existing = load_topic_files()
    existing_text = "\n\n".join(existing.values()) if existing else "(no existing topics)"

    formatted = _format_entries(new_entries)
    prompt = TOPIC_SYNC_PROMPT.format(
        existing_topics=existing_text,
        new_entries=formatted,
    )
    result = call_ollama(prompt)

    new_topics = parse_topic_document(result)

    # Write new/updated topic files
    for slug, section in new_topics.items():
        save_topic_file(slug, section)

    # Delete topic files absent from the output
    for old_slug in existing:
        if old_slug not in new_topics:
            delete_topic_file(old_slug)

    output(f"Topics updated ({len(new_topics)} topics in data/synthesis/).")

    # Phase 2: Context generation
    _generate_context(output=output)

    # Phase 3: Housekeeping
    rotate_rawlog()
    set_last_sync_time(new_entries[-1].time)
    handle_profile(output=output)


# --- Resynth ---

def handle_resynth(output: Writer = print) -> None:
    """Full rewrite of topic files from all entries using the deep model."""
    deep_model = load_deep_model()
    output(f"Deep resynthesis using {deep_model}...")

    all_entries = parse_rawlog_full()
    if not all_entries:
        output("No entries to synthesize.")
        return

    formatted = _format_entries(all_entries)
    prompt = TOPIC_RESYNTH_PROMPT.format(all_entries=formatted)
    result = call_ollama(prompt, model=deep_model)

    new_topics = parse_topic_document(result)

    # Remove all existing topic files
    existing = load_topic_files()
    for slug in existing:
        delete_topic_file(slug)

    # Write new topic files
    for slug, section in new_topics.items():
        save_topic_file(slug, section)

    output(f"Topics rewritten ({len(new_topics)} topics in data/synthesis/).")

    # Generate context
    _generate_context(output=output)

    # Update sync timestamp to most recent entry
    set_last_sync_time(all_entries[-1].time)
