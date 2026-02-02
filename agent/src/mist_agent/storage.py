"""File-path constants, raw-input persistence, and rawLog parsing (JSONL)."""

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

RAWLOG_PATH = Path("data/notes/rawLog.jsonl")
ARCHIVE_PATH = Path("data/notes/archive.jsonl")
TOPICS_DIR = Path("data/topics")
TOPIC_INDEX_PATH = Path("data/topics/index.json")
SYNTHESIS_DIR = Path("data/synthesis")
CONTEXT_PATH = Path("data/synthesis/context.md")
LAST_AGGREGATE_PATH = Path("data/state/last_aggregate.txt")
LAST_SYNC_PATH = Path("data/state/last_sync.txt")


@dataclass
class RawLogEntry:
    time: str
    source: str
    text: str


@dataclass
class TopicInfo:
    id: int
    name: str
    slug: str
    created: str


# --- JSONL read/write helpers ---

def _parse_jsonl_file(path: Path) -> list[RawLogEntry]:
    """Parse a JSONL file into a list of RawLogEntry objects."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    entries = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            entries.append(RawLogEntry(
                time=obj["time"],
                source=obj["source"],
                text=obj["text"],
            ))
        except (json.JSONDecodeError, KeyError):
            continue
    return entries


def _entry_to_jsonl(entry: RawLogEntry) -> str:
    """Serialize a RawLogEntry to a single JSON line."""
    return json.dumps({"time": entry.time, "source": entry.source, "text": entry.text})


# --- Raw log ---

def save_raw_input(text: str, source: str = "terminal") -> None:
    """Append a timestamped JSONL entry to the raw log."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    entry = RawLogEntry(time=timestamp, source=source, text=text.strip())
    RAWLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAWLOG_PATH, "a", encoding="utf-8") as f:
        f.write(_entry_to_jsonl(entry) + "\n")


def parse_rawlog() -> list[RawLogEntry]:
    """Parse rawLog.jsonl into a list of RawLogEntry objects."""
    return _parse_jsonl_file(RAWLOG_PATH)


def parse_archive() -> list[RawLogEntry]:
    """Parse archive.jsonl into a list of RawLogEntry objects."""
    return _parse_jsonl_file(ARCHIVE_PATH)


def parse_all_entries() -> list[RawLogEntry]:
    """Parse archive + rawLog + all topic noteLogs, deduplicated and sorted."""
    seen: set[tuple[str, str]] = set()
    all_entries: list[RawLogEntry] = []

    sources = [parse_archive(), parse_rawlog()]
    index = load_topic_index()
    for topic in index:
        sources.append(load_topic_notelog(topic.slug))

    for entries in sources:
        for e in entries:
            key = (e.time, e.text)
            if key not in seen:
                seen.add(key)
                all_entries.append(e)

    all_entries.sort(key=lambda e: e.time)
    return all_entries


def append_to_archive(entries: list[RawLogEntry]) -> None:
    """Append JSONL entries to archive.jsonl."""
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVE_PATH, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(_entry_to_jsonl(entry) + "\n")


def clear_rawlog() -> None:
    """Truncate rawLog.jsonl."""
    RAWLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    RAWLOG_PATH.write_text("", encoding="utf-8")


def write_rawlog(entries: list[RawLogEntry]) -> None:
    """Overwrite rawLog.jsonl with the given entries."""
    RAWLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAWLOG_PATH, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(_entry_to_jsonl(entry) + "\n")


def reset_topics() -> int:
    """Move all noteLog entries back to rawLog, wipe topics dir and timestamps.

    Returns the number of entries restored to rawLog.
    """
    # Collect all noteLog entries
    index = load_topic_index()
    all_entries: list[RawLogEntry] = []
    for topic in index:
        all_entries.extend(load_topic_notelog(topic.slug))

    # Deduplicate and sort
    seen: set[tuple[str, str]] = set()
    unique: list[RawLogEntry] = []
    for e in all_entries:
        key = (e.time, e.text)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    unique.sort(key=lambda e: e.time)

    # Write back to rawLog (append to any existing entries)
    if unique:
        RAWLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RAWLOG_PATH, "a", encoding="utf-8") as f:
            for entry in unique:
                f.write(_entry_to_jsonl(entry) + "\n")

    # Wipe topics directory
    if TOPICS_DIR.exists():
        shutil.rmtree(TOPICS_DIR)

    # Clear aggregate timestamp
    if LAST_AGGREGATE_PATH.exists():
        LAST_AGGREGATE_PATH.unlink()

    return len(unique)


# --- Aggregate timestamp ---

def get_last_aggregate_time() -> str | None:
    """Return the ISO timestamp of the last aggregated entry, or None."""
    try:
        ts = LAST_AGGREGATE_PATH.read_text(encoding="utf-8").strip()
        return ts or None
    except FileNotFoundError:
        return None


def set_last_aggregate_time(ts: str) -> None:
    """Record the ISO timestamp of the most recently aggregated entry."""
    LAST_AGGREGATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_AGGREGATE_PATH.write_text(ts, encoding="utf-8")


# --- Sync timestamp ---

def get_last_sync_time() -> str | None:
    """Return the ISO timestamp of the last synced entry, or None."""
    try:
        ts = LAST_SYNC_PATH.read_text(encoding="utf-8").strip()
        return ts or None
    except FileNotFoundError:
        return None


def set_last_sync_time(ts: str) -> None:
    """Record the ISO timestamp of the most recently synced entry."""
    LAST_SYNC_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_SYNC_PATH.write_text(ts, encoding="utf-8")


# --- Topic index ---

def load_topic_index() -> list[TopicInfo]:
    """Read data/topics/index.json, returning [] if missing."""
    try:
        content = TOPIC_INDEX_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        items = json.loads(content)
    except json.JSONDecodeError:
        return []
    return [
        TopicInfo(id=t["id"], name=t["name"], slug=t["slug"], created=t["created"])
        for t in items
    ]


def save_topic_index(topics: list[TopicInfo]) -> None:
    """Write data/topics/index.json."""
    TOPIC_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {"id": t.id, "name": t.name, "slug": t.slug, "created": t.created}
        for t in topics
    ]
    TOPIC_INDEX_PATH.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def add_topic(name: str, slug: str) -> TopicInfo:
    """Create a new topic entry + directory, return the TopicInfo."""
    index = load_topic_index()
    next_id = max((t.id for t in index), default=0) + 1
    created = datetime.now().isoformat(timespec="seconds")
    topic = TopicInfo(id=next_id, name=name, slug=slug, created=created)
    index.append(topic)
    save_topic_index(index)
    # Create topic directory with empty noteLog
    topic_dir = TOPICS_DIR / slug
    topic_dir.mkdir(parents=True, exist_ok=True)
    notelog = topic_dir / "noteLog.jsonl"
    if not notelog.exists():
        notelog.write_text("", encoding="utf-8")
    return topic


def find_topic(identifier: str, index: list[TopicInfo] | None = None) -> TopicInfo | None:
    """Look up a topic by id (numeric string) or slug."""
    if index is None:
        index = load_topic_index()
    # Try by id
    try:
        tid = int(identifier)
        for t in index:
            if t.id == tid:
                return t
    except ValueError:
        pass
    # Try by slug
    slug = identifier.lower().strip()
    for t in index:
        if t.slug == slug:
            return t
    return None


# --- Per-topic noteLog and synthesis ---

def append_to_topic_notelog(slug: str, entries: list[RawLogEntry]) -> None:
    """Append JSONL entries to a topic's noteLog.jsonl."""
    notelog = TOPICS_DIR / slug / "noteLog.jsonl"
    notelog.parent.mkdir(parents=True, exist_ok=True)
    with open(notelog, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(_entry_to_jsonl(entry) + "\n")


def load_topic_notelog(slug: str) -> list[RawLogEntry]:
    """Read a topic's noteLog.jsonl."""
    return _parse_jsonl_file(TOPICS_DIR / slug / "noteLog.jsonl")


def load_topic_about(slug: str) -> str:
    """Read a topic's about.md, returning '' if missing."""
    path = TOPICS_DIR / slug / "about.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def save_topic_about(slug: str, content: str) -> None:
    """Write a topic's about.md."""
    topic_dir = TOPICS_DIR / slug
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "about.md").write_text(content.strip() + "\n", encoding="utf-8")


def load_topic_synthesis(slug: str) -> str:
    """Read a topic's synthesis.md, returning '' if missing."""
    path = TOPICS_DIR / slug / "synthesis.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def save_topic_synthesis(slug: str, content: str) -> None:
    """Write a topic's synthesis.md."""
    topic_dir = TOPICS_DIR / slug
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "synthesis.md").write_text(content.strip() + "\n", encoding="utf-8")


# --- Per-topic synthesis files (for context generation) ---

def load_topic_files() -> dict[str, str]:
    """Read all topic synthesis files, keyed by slug.

    Returns {slug: synthesis_content}.
    """
    index = load_topic_index()
    topics = {}
    for t in index:
        content = load_topic_synthesis(t.slug)
        if content:
            topics[t.slug] = content
    return topics


# --- Context file ---

def load_context() -> str:
    """Read context.md, returning '' if missing."""
    try:
        return CONTEXT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def save_context(text: str) -> None:
    """Write the condensed context summary."""
    SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)
    CONTEXT_PATH.write_text(text.strip() + "\n", encoding="utf-8")
