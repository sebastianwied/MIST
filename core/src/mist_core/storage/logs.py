"""JSONL helpers for note buffers and log files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LogEntry:
    """A single timestamped log entry."""

    time: str
    source: str
    text: str


def parse_jsonl(path: Path) -> list[LogEntry]:
    """Parse a JSONL file into LogEntry objects. Returns [] if missing."""
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
            entries.append(LogEntry(
                time=obj["time"],
                source=obj["source"],
                text=obj["text"],
            ))
        except (json.JSONDecodeError, KeyError):
            continue
    return entries


def _entry_to_json(entry: LogEntry) -> str:
    return json.dumps({"time": entry.time, "source": entry.source, "text": entry.text})


def append_jsonl(path: Path, entries: list[LogEntry]) -> None:
    """Append entries to a JSONL file, creating it if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for entry in entries:
            f.write(_entry_to_json(entry) + "\n")


def write_jsonl(path: Path, entries: list[LogEntry]) -> None:
    """Overwrite a JSONL file with the given entries."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(_entry_to_json(entry) + "\n")
