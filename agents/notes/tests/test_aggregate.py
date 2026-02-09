"""Tests for aggregate — mock LLM, verify classification and routing."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from notes_agent.aggregate import (
    _extract_json_array,
    _parse_assignments,
    _slugify,
    _strip_code_fences,
)


class TestSlugify:
    def test_basic(self):
        assert _slugify("Machine Learning") == "machine-learning"

    def test_special_chars(self):
        assert _slugify("C++ & Python") == "c-python"

    def test_strip_hyphens(self):
        assert _slugify("  hello world  ") == "hello-world"


class TestStripCodeFences:
    def test_no_fences(self):
        assert _strip_code_fences('[{"a": 1}]') == '[{"a": 1}]'

    def test_json_fences(self):
        assert _strip_code_fences('```json\n[{"a": 1}]\n```') == '[{"a": 1}]'


class TestExtractJsonArray:
    def test_simple(self):
        result = _extract_json_array('text [1, 2, 3] more')
        assert result == "[1, 2, 3]"

    def test_nested(self):
        result = _extract_json_array('[{"a": [1, 2]}, {"b": 3}]')
        assert result == '[{"a": [1, 2]}, {"b": 3}]'

    def test_no_array(self):
        assert _extract_json_array("no arrays here") is None


class TestParseAssignments:
    def test_valid_json(self):
        raw = '[{"index": 0, "topic_slug": "ml"}]'
        result = _parse_assignments(raw)
        assert len(result) == 1
        assert result[0]["topic_slug"] == "ml"

    def test_code_fenced(self):
        raw = '```json\n[{"index": 0, "new_topic": "Science"}]\n```'
        result = _parse_assignments(raw)
        assert len(result) == 1
        assert result[0]["new_topic"] == "Science"

    def test_embedded_in_text(self):
        raw = 'Here are the assignments:\n[{"index": 0, "topic_slug": "ml"}]\nDone.'
        result = _parse_assignments(raw)
        assert len(result) == 1

    def test_invalid(self):
        assert _parse_assignments("not json") == []
