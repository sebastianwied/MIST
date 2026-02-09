"""Tests for mist_core.storage.logs."""

from mist_core.storage.logs import LogEntry, append_jsonl, parse_jsonl, write_jsonl


class TestParseJsonl:
    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("", encoding="utf-8")
        assert parse_jsonl(f) == []

    def test_missing_file(self, tmp_path):
        assert parse_jsonl(tmp_path / "missing.jsonl") == []

    def test_valid_entries(self, tmp_path):
        f = tmp_path / "log.jsonl"
        f.write_text(
            '{"time":"2024-01-01T00:00:00","source":"terminal","text":"hello"}\n'
            '{"time":"2024-01-01T00:01:00","source":"api","text":"world"}\n',
            encoding="utf-8",
        )
        entries = parse_jsonl(f)
        assert len(entries) == 2
        assert entries[0].text == "hello"
        assert entries[1].source == "api"

    def test_skips_malformed_lines(self, tmp_path):
        f = tmp_path / "log.jsonl"
        f.write_text(
            '{"time":"t","source":"s","text":"good"}\n'
            "not json\n"
            '{"bad": "keys"}\n'
            '{"time":"t2","source":"s2","text":"also good"}\n',
            encoding="utf-8",
        )
        entries = parse_jsonl(f)
        assert len(entries) == 2


class TestWriteJsonl:
    def test_write_and_read_back(self, tmp_path):
        f = tmp_path / "out.jsonl"
        entries = [
            LogEntry(time="t1", source="s1", text="a"),
            LogEntry(time="t2", source="s2", text="b"),
        ]
        write_jsonl(f, entries)
        result = parse_jsonl(f)
        assert len(result) == 2
        assert result[0].text == "a"
        assert result[1].text == "b"

    def test_overwrite(self, tmp_path):
        f = tmp_path / "out.jsonl"
        write_jsonl(f, [LogEntry(time="t1", source="s", text="first")])
        write_jsonl(f, [LogEntry(time="t2", source="s", text="second")])
        result = parse_jsonl(f)
        assert len(result) == 1
        assert result[0].text == "second"


class TestAppendJsonl:
    def test_append_to_new_file(self, tmp_path):
        f = tmp_path / "sub" / "log.jsonl"
        append_jsonl(f, [LogEntry(time="t1", source="s", text="first")])
        result = parse_jsonl(f)
        assert len(result) == 1

    def test_append_to_existing(self, tmp_path):
        f = tmp_path / "log.jsonl"
        append_jsonl(f, [LogEntry(time="t1", source="s", text="first")])
        append_jsonl(f, [LogEntry(time="t2", source="s", text="second")])
        result = parse_jsonl(f)
        assert len(result) == 2
