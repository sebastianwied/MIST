"""Per-agent note storage: buffers, topics, synthesis, drafts."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..paths import Paths
from .logs import LogEntry, append_jsonl, parse_jsonl, write_jsonl


@dataclass
class TopicInfo:
    id: int
    name: str
    slug: str
    created: str


class NoteStorage:
    """File-based note storage scoped to a single agent.

    All paths are derived from Paths + agent_id, enabling test isolation.
    """

    def __init__(self, paths: Paths, agent_id: str) -> None:
        self.paths = paths
        self.agent_id = agent_id

    # ── Note buffer (raw input) ─────────────────────────────────────

    def save_raw_input(self, text: str, source: str = "terminal") -> None:
        """Append a timestamped entry to the agent's note buffer."""
        timestamp = datetime.now().isoformat(timespec="seconds")
        entry = LogEntry(time=timestamp, source=source, text=text.strip())
        buf = self.paths.agent_note_buffer(self.agent_id)
        append_jsonl(buf, [entry])

    def parse_buffer(self) -> list[LogEntry]:
        """Read the agent's note buffer."""
        return parse_jsonl(self.paths.agent_note_buffer(self.agent_id))

    def clear_buffer(self) -> None:
        """Truncate the agent's note buffer."""
        buf = self.paths.agent_note_buffer(self.agent_id)
        buf.parent.mkdir(parents=True, exist_ok=True)
        buf.write_text("", encoding="utf-8")

    def write_buffer(self, entries: list[LogEntry]) -> None:
        """Overwrite the agent's note buffer."""
        write_jsonl(self.paths.agent_note_buffer(self.agent_id), entries)

    # ── Topic index ─────────────────────────────────────────────────

    def load_topic_index(self) -> list[TopicInfo]:
        """Read the topic index, returning [] if missing."""
        path = self.paths.agent_topic_index(self.agent_id)
        try:
            content = path.read_text(encoding="utf-8")
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

    def save_topic_index(self, topics: list[TopicInfo]) -> None:
        """Write the topic index."""
        path = self.paths.agent_topic_index(self.agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            {"id": t.id, "name": t.name, "slug": t.slug, "created": t.created}
            for t in topics
        ]
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def add_topic(self, name: str, slug: str) -> TopicInfo:
        """Create a new topic entry + directory."""
        index = self.load_topic_index()
        next_id = max((t.id for t in index), default=0) + 1
        created = datetime.now().isoformat(timespec="seconds")
        topic = TopicInfo(id=next_id, name=name, slug=slug, created=created)
        index.append(topic)
        self.save_topic_index(index)
        topic_dir = self.paths.agent_topic_dir(self.agent_id, slug)
        topic_dir.mkdir(parents=True, exist_ok=True)
        note_buf = self.paths.agent_topic_note_buffer(self.agent_id, slug)
        if not note_buf.exists():
            note_buf.write_text("", encoding="utf-8")
        return topic

    def find_topic(self, identifier: str, index: list[TopicInfo] | None = None) -> TopicInfo | None:
        """Look up a topic by id (numeric string) or slug."""
        if index is None:
            index = self.load_topic_index()
        try:
            tid = int(identifier)
            for t in index:
                if t.id == tid:
                    return t
        except ValueError:
            pass
        slug = identifier.lower().strip()
        for t in index:
            if t.slug == slug:
                return t
        return None

    # ── Per-topic note buffer ───────────────────────────────────────

    def append_to_topic_buffer(self, slug: str, entries: list[LogEntry]) -> None:
        """Append entries to a topic's noteBuffer.jsonl."""
        buf = self.paths.agent_topic_note_buffer(self.agent_id, slug)
        append_jsonl(buf, entries)

    def load_topic_buffer(self, slug: str) -> list[LogEntry]:
        """Read a topic's noteBuffer.jsonl."""
        return parse_jsonl(self.paths.agent_topic_note_buffer(self.agent_id, slug))

    # ── Per-topic note feed and synthesis ───────────────────────────

    def load_topic_note_feed(self, slug: str) -> str:
        """Read a topic's noteFeed.md, returning '' if missing."""
        path = self.paths.agent_topic_note_feed(self.agent_id, slug)
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def save_topic_note_feed(self, slug: str, content: str) -> None:
        """Write a topic's noteFeed.md."""
        path = self.paths.agent_topic_note_feed(self.agent_id, slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")

    def load_topic_synthesis(self, slug: str) -> str:
        """Read a topic's synthesis.md, returning '' if missing."""
        path = self.paths.agent_topic_synthesis(self.agent_id, slug)
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def save_topic_synthesis(self, slug: str, content: str) -> None:
        """Write a topic's synthesis.md."""
        path = self.paths.agent_topic_synthesis(self.agent_id, slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.strip() + "\n", encoding="utf-8")

    # ── Drafts ──────────────────────────────────────────────────────

    @staticmethod
    def _slugify_title(title: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return slug or "untitled"

    def create_draft(self, title: str) -> tuple[str, Path]:
        """Create an empty .md draft. Returns (filename, path)."""
        drafts = self.paths.agent_drafts_dir(self.agent_id)
        drafts.mkdir(parents=True, exist_ok=True)
        date = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date}-{self._slugify_title(title)}.md"
        path = drafts / filename
        if not path.exists():
            path.write_text(f"# {title}\n\n", encoding="utf-8")
        return filename, path

    def list_drafts(self) -> list[str]:
        """List .md filenames in the drafts dir."""
        drafts = self.paths.agent_drafts_dir(self.agent_id)
        if not drafts.is_dir():
            return []
        return sorted(p.name for p in drafts.glob("*.md"))

    def load_draft(self, filename: str) -> str:
        """Read a draft note, returning '' if missing."""
        try:
            return (self.paths.agent_drafts_dir(self.agent_id) / filename).read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def save_draft(self, filename: str, content: str) -> None:
        """Write a draft note."""
        drafts = self.paths.agent_drafts_dir(self.agent_id)
        drafts.mkdir(parents=True, exist_ok=True)
        (drafts / filename).write_text(content, encoding="utf-8")

    # ── Per-topic long-form notes ───────────────────────────────────

    def _topic_notes_dir(self, slug: str) -> Path:
        return self.paths.agent_topic_dir(self.agent_id, slug) / "notes"

    def create_topic_note(self, slug: str, title: str) -> tuple[str, Path]:
        """Create an empty .md note in a topic's notes/ dir."""
        notes_dir = self._topic_notes_dir(slug)
        notes_dir.mkdir(parents=True, exist_ok=True)
        date = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date}-{self._slugify_title(title)}.md"
        path = notes_dir / filename
        if not path.exists():
            path.write_text(f"# {title}\n\n", encoding="utf-8")
        return filename, path

    def list_topic_notes(self, slug: str) -> list[str]:
        """List .md filenames in a topic's notes/ dir."""
        notes_dir = self._topic_notes_dir(slug)
        if not notes_dir.is_dir():
            return []
        return sorted(p.name for p in notes_dir.glob("*.md"))

    def load_topic_note(self, slug: str, filename: str) -> str:
        try:
            return (self._topic_notes_dir(slug) / filename).read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def save_topic_note(self, slug: str, filename: str, content: str) -> None:
        notes_dir = self._topic_notes_dir(slug)
        notes_dir.mkdir(parents=True, exist_ok=True)
        (notes_dir / filename).write_text(content, encoding="utf-8")

    # ── Merge topics ────────────────────────────────────────────────

    def merge_topics(self, source_slug: str, target_slug: str) -> int:
        """Merge source topic into target. Returns count of entries moved."""
        # 1. Move buffer entries
        entries = self.load_topic_buffer(source_slug)
        if entries:
            self.append_to_topic_buffer(target_slug, entries)

        # 2. Move note files
        source_notes = self._topic_notes_dir(source_slug)
        if source_notes.is_dir():
            target_notes = self._topic_notes_dir(target_slug)
            target_notes.mkdir(parents=True, exist_ok=True)
            for src_file in sorted(source_notes.glob("*.md")):
                dest = target_notes / src_file.name
                if dest.exists():
                    dest = target_notes / f"{source_slug}--{src_file.name}"
                src_file.rename(dest)

        # 3. Concatenate synthesis
        source_synth = self.load_topic_synthesis(source_slug)
        if source_synth:
            target_synth = self.load_topic_synthesis(target_slug)
            combined = f"{target_synth}\n\n---\n\n{source_synth}" if target_synth else source_synth
            self.save_topic_synthesis(target_slug, combined)

        # 4. Remove source from index
        index = self.load_topic_index()
        index = [t for t in index if t.slug != source_slug]
        self.save_topic_index(index)

        # 5. Delete source directory
        source_dir = self.paths.agent_topic_dir(self.agent_id, source_slug)
        if source_dir.exists():
            shutil.rmtree(source_dir)

        return len(entries)

    # ── Aggregate / sync timestamps ─────────────────────────────────

    def get_last_aggregate_time(self) -> str | None:
        try:
            ts = self.paths.agent_last_aggregate(self.agent_id).read_text(encoding="utf-8").strip()
            return ts or None
        except FileNotFoundError:
            return None

    def set_last_aggregate_time(self, ts: str) -> None:
        path = self.paths.agent_last_aggregate(self.agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ts, encoding="utf-8")

    def get_last_sync_time(self) -> str | None:
        try:
            ts = self.paths.agent_last_sync(self.agent_id).read_text(encoding="utf-8").strip()
            return ts or None
        except FileNotFoundError:
            return None

    def set_last_sync_time(self, ts: str) -> None:
        path = self.paths.agent_last_sync(self.agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(ts, encoding="utf-8")
