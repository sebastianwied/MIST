"""File-path constants, raw-input persistence, and rawLog parsing."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

RAWLOG_PATH = Path("data/notes/rawLog.md")
TO_SYNTH_PATH = Path("data/notes/toSynthesize.md")
JOURNAL_PATH = Path("data/agentJournal.md")
LAST_SUMMARIZED_PATH = Path("data/state/last_summarized.txt")

SYNTHESIS_DIR = Path("data/synthesis")
CONTEXT_PATH = Path("data/synthesis/context.md")
RAWLOG_ARCHIVE_PATH = Path("data/notes/rawLog_archive.md")
LAST_SYNC_PATH = Path("data/state/last_sync.txt")
RAWLOG_KEEP_COUNT = 50

_ENTRY_RE = re.compile(
    r"---\s*\ntime:\s*(.+)\nsource:\s*(.+)\n---\s*\n(.*?)(?=\n---\s*\n|$)",
    re.DOTALL,
)


@dataclass
class RawLogEntry:
    time: str
    source: str
    text: str


def save_raw_input(text: str, source: str = "terminal") -> None:
    """Append a timestamped entry to the raw log."""
    timestamp = datetime.now().isoformat(timespec="seconds")
    entry = f"""---
time: {timestamp}
source: {source}
---

{text.strip()}
"""
    with open(RAWLOG_PATH, "a") as f:
        f.write("\n")
        f.write(entry)


def _parse_rawlog_file(path: Path) -> list[RawLogEntry]:
    """Parse a single rawLog-format file into entries."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    entries = []
    for m in _ENTRY_RE.finditer(content):
        entries.append(RawLogEntry(
            time=m.group(1).strip(),
            source=m.group(2).strip(),
            text=m.group(3).strip(),
        ))
    return entries


def parse_rawlog() -> list[RawLogEntry]:
    """Parse rawLog.md into a list of RawLogEntry objects."""
    return _parse_rawlog_file(RAWLOG_PATH)


def get_last_summarized_time() -> str | None:
    """Return the ISO timestamp of the last summarized entry, or None."""
    try:
        ts = LAST_SUMMARIZED_PATH.read_text(encoding="utf-8").strip()
        return ts or None
    except FileNotFoundError:
        return None


def set_last_summarized_time(ts: str) -> None:
    """Record the ISO timestamp of the most recently summarized entry."""
    LAST_SUMMARIZED_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_SUMMARIZED_PATH.write_text(ts, encoding="utf-8")


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


# --- Per-topic synthesis files ---

def load_topic_files() -> dict[str, str]:
    """Read all .md files in SYNTHESIS_DIR except context.md.

    Returns {stem: content}.
    """
    if not SYNTHESIS_DIR.exists():
        return {}
    topics = {}
    for p in sorted(SYNTHESIS_DIR.glob("*.md")):
        if p.name == "context.md":
            continue
        topics[p.stem] = p.read_text(encoding="utf-8").strip()
    return topics


def save_topic_file(slug: str, content: str) -> None:
    """Write a single topic file to SYNTHESIS_DIR."""
    SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)
    (SYNTHESIS_DIR / f"{slug}.md").write_text(content.strip() + "\n", encoding="utf-8")


def delete_topic_file(slug: str) -> None:
    """Remove a topic file if it exists."""
    path = SYNTHESIS_DIR / f"{slug}.md"
    if path.exists():
        path.unlink()


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


# --- rawLog archive and rotation ---

def parse_rawlog_full() -> list[RawLogEntry]:
    """Parse both rawLog_archive.md and rawLog.md, returning all entries in order."""
    archive = _parse_rawlog_file(RAWLOG_ARCHIVE_PATH)
    active = _parse_rawlog_file(RAWLOG_PATH)
    return archive + active


def format_rawlog_entries(entries: list[RawLogEntry]) -> str:
    """Re-serialize entries back to rawLog markdown format."""
    parts = []
    for e in entries:
        parts.append(f"---\ntime: {e.time}\nsource: {e.source}\n---\n\n{e.text}\n")
    return "\n".join(parts)


def rotate_rawlog(keep: int = RAWLOG_KEEP_COUNT) -> None:
    """Move old entries to archive, keeping only the most recent *keep* in rawLog."""
    entries = _parse_rawlog_file(RAWLOG_PATH)
    if len(entries) <= keep:
        return

    to_archive = entries[:-keep]
    to_keep = entries[-keep:]

    # Append to archive
    RAWLOG_ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    archive_text = format_rawlog_entries(to_archive)
    with open(RAWLOG_ARCHIVE_PATH, "a", encoding="utf-8") as f:
        f.write("\n")
        f.write(archive_text)

    # Rewrite active rawLog
    RAWLOG_PATH.write_text(format_rawlog_entries(to_keep), encoding="utf-8")
