"""Tests for mist_core.storage.notes."""

import pytest

from mist_core.paths import Paths
from mist_core.storage.logs import LogEntry
from mist_core.storage.notes import NoteStorage


@pytest.fixture
def paths(tmp_path):
    return Paths(root=tmp_path / "data")


@pytest.fixture
def notes(paths):
    paths.ensure_agent_dirs("test-agent")
    return NoteStorage(paths, "test-agent")


class TestNoteBuffer:
    def test_save_and_parse(self, notes):
        notes.save_raw_input("hello world")
        entries = notes.parse_buffer()
        assert len(entries) == 1
        assert entries[0].text == "hello world"
        assert entries[0].source == "terminal"

    def test_multiple_entries(self, notes):
        notes.save_raw_input("first")
        notes.save_raw_input("second", source="api")
        entries = notes.parse_buffer()
        assert len(entries) == 2

    def test_clear_buffer(self, notes):
        notes.save_raw_input("hello")
        notes.clear_buffer()
        assert notes.parse_buffer() == []

    def test_write_buffer(self, notes):
        entries = [
            LogEntry(time="t1", source="s", text="a"),
            LogEntry(time="t2", source="s", text="b"),
        ]
        notes.write_buffer(entries)
        result = notes.parse_buffer()
        assert len(result) == 2


class TestTopicIndex:
    def test_empty_initially(self, notes):
        assert notes.load_topic_index() == []

    def test_add_topic(self, notes):
        topic = notes.add_topic("Machine Learning", "ml")
        assert topic.name == "Machine Learning"
        assert topic.slug == "ml"
        assert topic.id == 1
        index = notes.load_topic_index()
        assert len(index) == 1

    def test_auto_increment_id(self, notes):
        notes.add_topic("A", "a")
        t2 = notes.add_topic("B", "b")
        assert t2.id == 2

    def test_find_topic_by_id(self, notes):
        notes.add_topic("ML", "ml")
        found = notes.find_topic("1")
        assert found is not None
        assert found.slug == "ml"

    def test_find_topic_by_slug(self, notes):
        notes.add_topic("ML", "ml")
        found = notes.find_topic("ml")
        assert found is not None
        assert found.name == "ML"

    def test_find_topic_missing(self, notes):
        assert notes.find_topic("nonexistent") is None


class TestTopicBuffer:
    def test_append_and_load(self, notes):
        notes.add_topic("ML", "ml")
        entries = [LogEntry(time="t1", source="s", text="note about ml")]
        notes.append_to_topic_buffer("ml", entries)
        result = notes.load_topic_buffer("ml")
        assert len(result) == 1
        assert result[0].text == "note about ml"


class TestTopicSynthesis:
    def test_empty_initially(self, notes):
        notes.add_topic("ML", "ml")
        assert notes.load_topic_synthesis("ml") == ""

    def test_save_and_load(self, notes):
        notes.add_topic("ML", "ml")
        notes.save_topic_synthesis("ml", "# ML Synthesis\n\nKey points...")
        result = notes.load_topic_synthesis("ml")
        assert "ML Synthesis" in result


class TestTopicNoteFeed:
    def test_empty_initially(self, notes):
        notes.add_topic("ML", "ml")
        assert notes.load_topic_note_feed("ml") == ""

    def test_save_and_load(self, notes):
        notes.add_topic("ML", "ml")
        notes.save_topic_note_feed("ml", "# Notes\n\nEntry 1")
        result = notes.load_topic_note_feed("ml")
        assert "Entry 1" in result


class TestDrafts:
    def test_create_draft(self, notes):
        filename, path = notes.create_draft("My Note")
        assert filename.endswith("-my-note.md")
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "# My Note" in content

    def test_list_drafts(self, notes):
        notes.create_draft("First")
        notes.create_draft("Second")
        drafts = notes.list_drafts()
        assert len(drafts) == 2

    def test_load_and_save_draft(self, notes):
        filename, _ = notes.create_draft("Test")
        notes.save_draft(filename, "Updated content")
        assert notes.load_draft(filename) == "Updated content"

    def test_load_missing_draft(self, notes):
        assert notes.load_draft("nonexistent.md") == ""


class TestTopicNotes:
    def test_create_and_list(self, notes):
        notes.add_topic("ML", "ml")
        filename, path = notes.create_topic_note("ml", "Deep Learning")
        assert path.exists()
        note_list = notes.list_topic_notes("ml")
        assert len(note_list) == 1

    def test_save_and_load(self, notes):
        notes.add_topic("ML", "ml")
        filename, _ = notes.create_topic_note("ml", "Test")
        notes.save_topic_note("ml", filename, "New content")
        assert notes.load_topic_note("ml", filename) == "New content"


class TestMergeTopics:
    def test_merge_moves_entries(self, notes):
        notes.add_topic("Source", "src")
        notes.add_topic("Target", "tgt")
        entries = [LogEntry(time="t1", source="s", text="from source")]
        notes.append_to_topic_buffer("src", entries)

        count = notes.merge_topics("src", "tgt")
        assert count == 1
        assert notes.load_topic_buffer("tgt")[0].text == "from source"

    def test_merge_removes_source_from_index(self, notes):
        notes.add_topic("Source", "src")
        notes.add_topic("Target", "tgt")
        notes.merge_topics("src", "tgt")
        index = notes.load_topic_index()
        slugs = [t.slug for t in index]
        assert "src" not in slugs
        assert "tgt" in slugs

    def test_merge_concatenates_synthesis(self, notes):
        notes.add_topic("Source", "src")
        notes.add_topic("Target", "tgt")
        notes.save_topic_synthesis("src", "Source synthesis")
        notes.save_topic_synthesis("tgt", "Target synthesis")
        notes.merge_topics("src", "tgt")
        result = notes.load_topic_synthesis("tgt")
        assert "Source synthesis" in result
        assert "Target synthesis" in result


class TestTimestamps:
    def test_aggregate_timestamp(self, notes):
        assert notes.get_last_aggregate_time() is None
        notes.set_last_aggregate_time("2024-01-01T00:00:00")
        assert notes.get_last_aggregate_time() == "2024-01-01T00:00:00"

    def test_sync_timestamp(self, notes):
        assert notes.get_last_sync_time() is None
        notes.set_last_sync_time("2024-01-01T00:00:00")
        assert notes.get_last_sync_time() == "2024-01-01T00:00:00"


class TestNamespaceIsolation:
    def test_different_agents_isolated(self, paths):
        paths.ensure_agent_dirs("agent-a")
        paths.ensure_agent_dirs("agent-b")
        a = NoteStorage(paths, "agent-a")
        b = NoteStorage(paths, "agent-b")

        a.save_raw_input("from agent a")
        b.save_raw_input("from agent b")

        assert len(a.parse_buffer()) == 1
        assert a.parse_buffer()[0].text == "from agent a"
        assert len(b.parse_buffer()) == 1
        assert b.parse_buffer()[0].text == "from agent b"
