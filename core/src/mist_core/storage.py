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


# --- Per-topic long-form notes ---

DRAFTS_DIR = Path("data/notes/drafts")


def _slugify_title(title: str) -> str:
    """Turn a note title into a filename-safe slug."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "untitled"


def create_draft_note(title: str) -> tuple[str, Path]:
    """Create an empty .md note in the drafts dir. Returns (filename, path)."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date}-{_slugify_title(title)}.md"
    path = DRAFTS_DIR / filename
    if not path.exists():
        path.write_text(f"# {title}\n\n", encoding="utf-8")
    return filename, path


def list_draft_notes() -> list[str]:
    """List .md filenames in the drafts dir."""
    if not DRAFTS_DIR.is_dir():
        return []
    return sorted(p.name for p in DRAFTS_DIR.glob("*.md"))


def load_draft_note(filename: str) -> str:
    """Read a draft note, returning '' if missing."""
    try:
        return (DRAFTS_DIR / filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def save_draft_note(filename: str, content: str) -> None:
    """Write a draft note."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    (DRAFTS_DIR / filename).write_text(content, encoding="utf-8")


def create_topic_note(slug: str, title: str) -> tuple[str, Path]:
    """Create an empty .md note in a topic's notes/ dir. Returns (filename, path)."""
    notes_dir = TOPICS_DIR / slug / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date}-{_slugify_title(title)}.md"
    path = notes_dir / filename
    if not path.exists():
        path.write_text(f"# {title}\n\n", encoding="utf-8")
    return filename, path


def list_topic_notes(slug: str) -> list[str]:
    """List .md filenames in a topic's notes/ dir."""
    notes_dir = TOPICS_DIR / slug / "notes"
    if not notes_dir.is_dir():
        return []
    return sorted(p.name for p in notes_dir.glob("*.md"))


def load_topic_note(slug: str, filename: str) -> str:
    """Read a topic note, returning '' if missing."""
    path = TOPICS_DIR / slug / "notes" / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def save_topic_note(slug: str, filename: str, content: str) -> None:
    """Write a topic note."""
    notes_dir = TOPICS_DIR / slug / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    (notes_dir / filename).write_text(content, encoding="utf-8")


def file_draft_to_topic(filename: str, slug: str) -> str:
    """Move a draft note into a topic's notes/ directory.

    Handles filename collisions by prefixing with 'draft--'.
    Returns the final filename used.
    """
    content = (DRAFTS_DIR / filename).read_text(encoding="utf-8")
    target = TOPICS_DIR / slug / "notes" / filename
    final_filename = filename
    if target.exists():
        final_filename = f"draft--{filename}"
    save_topic_note(slug, final_filename, content)
    (DRAFTS_DIR / filename).unlink()
    return final_filename


def merge_topics(source_slug: str, target_slug: str) -> int:
    """Merge source topic into target: entries, notes, synthesis, about.

    Moves all noteLog entries, .md notes, synthesis, and about content
    from source into target, removes source from index, and deletes
    source directory.

    Returns the number of noteLog entries moved.
    """
    # 1. Move noteLog entries
    entries = load_topic_notelog(source_slug)
    if entries:
        append_to_topic_notelog(target_slug, entries)

    # 2. Move .md note files
    source_notes_dir = TOPICS_DIR / source_slug / "notes"
    if source_notes_dir.is_dir():
        target_notes_dir = TOPICS_DIR / target_slug / "notes"
        target_notes_dir.mkdir(parents=True, exist_ok=True)
        for src_file in sorted(source_notes_dir.glob("*.md")):
            if src_file.name == "notelog.md":
                continue  # auto-generated, will be regenerated
            dest = target_notes_dir / src_file.name
            if dest.exists():
                dest = target_notes_dir / f"{source_slug}--{src_file.name}"
            src_file.rename(dest)

    # 3. Concatenate synthesis
    source_synth = load_topic_synthesis(source_slug)
    if source_synth:
        target_synth = load_topic_synthesis(target_slug)
        if target_synth:
            combined = target_synth + "\n\n---\n\n" + source_synth
        else:
            combined = source_synth
        save_topic_synthesis(target_slug, combined)

    # 4. Concatenate about
    source_about = load_topic_about(source_slug)
    if source_about:
        target_about = load_topic_about(target_slug)
        if target_about:
            combined = target_about + "\n\n---\n\n" + source_about
        else:
            combined = source_about
        save_topic_about(target_slug, combined)

    # 5. Remove source from index
    index = load_topic_index()
    index = [t for t in index if t.slug != source_slug]
    save_topic_index(index)

    # 6. Delete source directory
    source_dir = TOPICS_DIR / source_slug
    if source_dir.exists():
        shutil.rmtree(source_dir)

    return len(entries)


def save_topic_notelog_md(slug: str, entries: list[RawLogEntry]) -> None:
    """Write all noteLog entries as formatted markdown to notes/notelog.md."""
    notes_dir = TOPICS_DIR / slug / "notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# NoteLog\n"]
    for e in entries:
        lines.append(f"**{e.time}** ({e.source})")
        lines.append(e.text)
        lines.append("\n---\n")
    (notes_dir / "notelog.md").write_text("\n".join(lines), encoding="utf-8")
