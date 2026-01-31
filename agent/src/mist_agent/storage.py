"""File-path constants, raw-input persistence, and rawLog parsing."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

RAWLOG_PATH = Path("data/notes/rawLog.md")
TO_SYNTH_PATH = Path("data/notes/toSynthesize.md")
JOURNAL_PATH = Path("data/agentJournal.md")
SYNTHESIS_PATH = Path("data/notes/synthesis.md")
LAST_SUMMARIZED_PATH = Path("data/state/last_summarized.txt")

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


def parse_rawlog() -> list[RawLogEntry]:
    """Parse rawLog.md into a list of RawLogEntry objects."""
    try:
        content = RAWLOG_PATH.read_text(encoding="utf-8")
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
