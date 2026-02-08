"""Core aggregate handler: classify entries into topics and route them."""

import json
import re
from typing import Callable

from mist_core.ollama_client import call_ollama
from mist_core.storage import (
    RawLogEntry,
    TopicInfo,
    add_topic,
    append_to_archive,
    append_to_topic_notelog,
    find_topic,
    load_topic_about,
    load_topic_index,
    merge_topics,
    parse_rawlog,
    reset_topics,
    save_topic_about,
    set_last_aggregate_time,
    write_rawlog,
)
from mist_core.types import Writer

from .notes import _format_entries
from .profile_command import handle_profile
from .prompts import AGGREGATE_ASSIGNMENT_PROMPT
from .synthesis import _slugify


def _build_existing_topics_text(index: list[TopicInfo]) -> str:
    """Format the topic index for the LLM prompt, including about descriptions."""
    if not index:
        return "(no existing topics)"
    lines = []
    for t in index:
        about = load_topic_about(t.slug)
        if about:
            lines.append(f"- {t.slug}: {t.name} — {about}")
        else:
            lines.append(f"- {t.slug}: {t.name}")
    return "\n".join(lines)


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` wrapping from LLM output."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _extract_json_array(text: str) -> str | None:
    """Find the first top-level JSON array in text, handling nested brackets."""
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


def _parse_assignments(raw_llm_output: str, entry_count: int) -> list[dict]:
    """Parse JSON assignment array from LLM output."""
    cleaned = _strip_code_fences(raw_llm_output)
    # Try parsing the whole thing first
    try:
        assignments = json.loads(cleaned)
        if isinstance(assignments, list):
            return assignments
    except json.JSONDecodeError:
        pass
    # Fall back to extracting the first JSON array from the text
    array_str = _extract_json_array(raw_llm_output)
    if array_str:
        try:
            assignments = json.loads(array_str)
            if isinstance(assignments, list):
                return assignments
        except json.JSONDecodeError:
            pass
    return []


MAX_CLASSIFY_RETRIES = 3


def classify_entries(
    entries: list[RawLogEntry],
    index: list[TopicInfo],
    output: Writer = print,
) -> tuple[list[dict], dict[str, str]]:
    """Call LLM to classify entries into topics.

    Retries up to MAX_CLASSIFY_RETRIES times on parse failure.

    Returns (assignments, proposed_new_topics).
    - assignments: parsed JSON list from LLM
    - proposed_new_topics: {name: slug} for topics that don't exist yet
    """
    existing_text = _build_existing_topics_text(index)
    formatted = _format_entries(entries)
    prompt = AGGREGATE_ASSIGNMENT_PROMPT.format(
        existing_topics=existing_text,
        new_entries=formatted,
    )

    for attempt in range(1, MAX_CLASSIFY_RETRIES + 1):
        result = call_ollama(prompt, command="aggregate")
        assignments = _parse_assignments(result, len(entries))
        if assignments:
            break
        if attempt < MAX_CLASSIFY_RETRIES:
            output(f"LLM returned unparseable response (attempt {attempt}/{MAX_CLASSIFY_RETRIES}), retrying...")
        else:
            output("LLM response (failed to parse as JSON):")
            output(result[:500])
            return [], {}

    existing_slugs = {t.slug for t in index}
    proposed: dict[str, str] = {}
    for a in assignments:
        new_name = a.get("new_topic")
        if new_name and new_name != "__skip__":
            slug = _slugify(new_name)
            if slug and slug not in existing_slugs and new_name not in proposed:
                proposed[new_name] = slug

    return assignments, proposed


def route_entries(
    entries: list[RawLogEntry],
    assignments: list[dict],
    confirmed: dict[str, str],
    skipped: set[str],
    index: list[TopicInfo],
) -> tuple[int, int]:
    """Route classified entries to topic noteLogs.

    Args:
        entries: the original rawLog entries
        assignments: LLM assignment output
        confirmed: {proposed_name: final_name_or_"yes"} for accepted new topics
        skipped: set of proposed names that were rejected
        index: current topic index

    Returns (routed_count, new_topic_count).
    """
    # Create confirmed new topics
    new_topic_count = 0
    slug_map: dict[str, str] = {}  # name -> slug for new topics
    for proposed_name, action in confirmed.items():
        if proposed_name in skipped:
            continue
        original_slug = _slugify(proposed_name)
        if action == "yes":
            final_name = proposed_name
        else:
            final_name = action  # renamed
        final_slug = _slugify(final_name)
        topic = add_topic(final_name, final_slug)
        slug_map[proposed_name] = topic.slug
        new_topic_count += 1

    # Refresh index after creating topics
    index = load_topic_index()
    existing_slugs = {t.slug for t in index}

    # Route entries — track which ones are handled vs. rejected
    topic_entries: dict[str, list[RawLogEntry]] = {}
    handled_indices: set[int] = set()  # indices that were routed or skipped
    routed_count = 0
    for a in assignments:
        idx = a.get("index")
        if idx is None or idx < 0 or idx >= len(entries):
            continue
        entry = entries[idx]

        slug = a.get("topic_slug")
        new_name = a.get("new_topic")

        # __skip__ entries are handled (noise, don't keep in rawLog)
        if slug == "__skip__":
            handled_indices.add(idx)
            continue

        # Entries for rejected topics stay in rawLog for next aggregate
        if new_name and new_name in skipped:
            continue

        if new_name:
            target_slug = slug_map.get(new_name)
            if not target_slug:
                continue
        elif slug and slug in existing_slugs:
            target_slug = slug
        else:
            continue

        if target_slug not in topic_entries:
            topic_entries[target_slug] = []
        topic_entries[target_slug].append(entry)
        handled_indices.add(idx)
        routed_count += 1

    # Write entries to topic noteLogs
    for slug, ents in topic_entries.items():
        append_to_topic_notelog(slug, ents)

    # Split entries: handled ones get archived, rejected ones stay in rawLog
    handled = [entries[i] for i in sorted(handled_indices)]
    leftover = [entries[i] for i in range(len(entries)) if i not in handled_indices]

    # Profile extraction on handled entries
    if handled:
        handle_profile(output=lambda *a, **kw: None, entries=handled)

    # Archive handled entries, rewrite rawLog with leftovers only
    append_to_archive(handled)
    write_rawlog(leftover)
    if handled:
        set_last_aggregate_time(handled[-1].time)

    return routed_count, new_topic_count


def handle_aggregate(
    output: Writer = print,
    confirm_fn: Callable[[str], str] | None = None,
) -> None:
    """All-in-one aggregate for the REPL: classify, confirm, route."""
    entries = parse_rawlog()
    if not entries:
        output("No entries to aggregate.")
        return

    index = load_topic_index()
    output(f"Classifying {len(entries)} entries...")
    assignments, proposed = classify_entries(entries, index, output=output)

    if not assignments:
        return

    # Confirm new topics
    confirmed: dict[str, str] = {}
    skipped: set[str] = set()
    for name in proposed:
        if confirm_fn:
            answer = confirm_fn(name)
            if answer.lower() == "no":
                skipped.add(name)
            elif answer.lower() == "yes":
                confirmed[name] = "yes"
            else:
                confirmed[name] = answer  # renamed
        else:
            confirmed[name] = "yes"

    routed, new_topics = route_entries(entries, assignments, confirmed, skipped, index)
    output(f"Aggregated {routed} entries across {len(load_topic_index())} topics ({new_topics} new).")


def handle_topic_add(name: str, output: Writer = print) -> None:
    """Manually create a new topic."""
    slug = _slugify(name)
    if not slug:
        output("Invalid topic name.")
        return
    existing = find_topic(slug)
    if existing:
        output(f"Topic '{existing.name}' ({existing.slug}) already exists.")
        return
    topic = add_topic(name, slug)
    output(f"Created topic [{topic.id}] {topic.slug}: {topic.name}")


def handle_topic_about(identifier: str, text: str, output: Writer = print) -> None:
    """Set or view a topic's about description."""
    topic = find_topic(identifier)
    if topic is None:
        output(f"Topic '{identifier}' not found. Use 'view topics' to list.")
        return
    if not text:
        about = load_topic_about(topic.slug)
        if about:
            output(f"[{topic.id}] {topic.name}: {about}")
        else:
            output(f"[{topic.id}] {topic.name}: (no description)")
        return
    save_topic_about(topic.slug, text)
    output(f"Description set for '{topic.name}'.")


def handle_topic_merge(source_id: str, target_id: str, output: Writer = print) -> None:
    """Merge source topic into target topic."""
    if not target_id:
        output("Usage: topic merge <source> <target>")
        return
    index = load_topic_index()
    source = find_topic(source_id, index)
    if source is None:
        output(f"Source topic '{source_id}' not found. Use 'view topics' to list.")
        return
    target = find_topic(target_id, index)
    if target is None:
        output(f"Target topic '{target_id}' not found. Use 'view topics' to list.")
        return
    if source.slug == target.slug:
        output("Source and target are the same topic.")
        return
    count = merge_topics(source.slug, target.slug)
    output(f"Merged {count} entries from '{source.name}' into '{target.name}'. Source topic deleted.")


def handle_reset_topics(output: Writer = print) -> None:
    """Move all noteLog entries back to rawLog and wipe all topics."""
    count = reset_topics()
    output(f"Reset complete. {count} entries restored to rawLog. Topics cleared.")
    output("Run 'aggregate' to reclassify.")
