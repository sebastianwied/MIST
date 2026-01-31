"""File-path constants and raw-input persistence."""

from datetime import datetime
from pathlib import Path

RAWLOG_PATH = Path("data/notes/rawLog.md")
TO_SYNTH_PATH = Path("data/notes/toSynthesize.md")
JOURNAL_PATH = Path("data/agentJournal.md")


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
