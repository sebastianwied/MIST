"""Tests for admin extraction — mock LLM, verify task/event extraction."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from mist_core.admin.extraction import (
    _strip_code_fences,
    apply_extracted_items,
    extract_items,
)
from mist_core.db import Database
from mist_core.llm.client import OllamaClient
from mist_core.llm.queue import LLMQueue
from mist_core.paths import Paths
from mist_core.storage.events import EventStore
from mist_core.storage.settings import Settings
from mist_core.storage.tasks import TaskStore


@pytest.fixture
def paths(tmp_path):
    return Paths(root=tmp_path / "data")


@pytest.fixture
def db(paths):
    database = Database(paths.db)
    database.connect()
    database.init_schema()
    yield database
    database.close()


@pytest.fixture
def tasks_store(db):
    return TaskStore(db)


@pytest.fixture
def events_store(db):
    return EventStore(db)


class TestStripCodeFences:
    def test_no_fences(self):
        assert _strip_code_fences('{"a": 1}') == '{"a": 1}'

    def test_json_fences(self):
        assert _strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_plain_fences(self):
        assert _strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'


class TestExtractItems:
    async def test_extracts_tasks_and_events(self, paths):
        """Mock the LLM to return valid JSON, verify parsing."""
        settings = Settings(paths)
        llm_client = OllamaClient(settings)
        llm_queue = LLMQueue(llm_client)

        expected = {
            "tasks": [{"title": "Buy milk", "due_date": "2025-12-31"}],
            "events": [{"title": "Meeting", "start_time": "2025-12-25T14:00"}],
        }

        with patch.object(llm_queue, "submit", new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = json.dumps(expected)
            result = await extract_items("I need to buy milk by year-end and have a meeting on Christmas", llm_queue)

        assert len(result["tasks"]) == 1
        assert result["tasks"][0]["title"] == "Buy milk"
        assert len(result["events"]) == 1
        assert result["events"][0]["title"] == "Meeting"

    async def test_handles_invalid_json(self, paths):
        settings = Settings(paths)
        llm_client = OllamaClient(settings)
        llm_queue = LLMQueue(llm_client)

        with patch.object(llm_queue, "submit", new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = "not json at all"
            result = await extract_items("hello", llm_queue)

        assert result == {"tasks": [], "events": []}

    async def test_handles_llm_error(self, paths):
        settings = Settings(paths)
        llm_client = OllamaClient(settings)
        llm_queue = LLMQueue(llm_client)

        with patch.object(llm_queue, "submit", new_callable=AsyncMock) as mock_submit:
            mock_submit.side_effect = RuntimeError("LLM down")
            result = await extract_items("hello", llm_queue)

        assert result == {"tasks": [], "events": []}

    async def test_handles_code_fenced_json(self, paths):
        settings = Settings(paths)
        llm_client = OllamaClient(settings)
        llm_queue = LLMQueue(llm_client)

        expected = {"tasks": [{"title": "Test", "due_date": None}], "events": []}

        with patch.object(llm_queue, "submit", new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = f"```json\n{json.dumps(expected)}\n```"
            result = await extract_items("test", llm_queue)

        assert len(result["tasks"]) == 1

    async def test_handles_non_dict_response(self, paths):
        settings = Settings(paths)
        llm_client = OllamaClient(settings)
        llm_queue = LLMQueue(llm_client)

        with patch.object(llm_queue, "submit", new_callable=AsyncMock) as mock_submit:
            mock_submit.return_value = '["not", "a", "dict"]'
            result = await extract_items("test", llm_queue)

        assert result == {"tasks": [], "events": []}


class TestApplyExtractedItems:
    async def test_creates_tasks(self, tasks_store, events_store):
        items = {
            "tasks": [
                {"title": "Buy milk", "due_date": "2025-12-31"},
                {"title": "Call dentist", "due_date": None},
            ],
            "events": [],
        }
        created = await apply_extracted_items(items, tasks_store, events_store)
        assert len(created) == 2
        assert "Buy milk" in created[0]
        assert "Call dentist" in created[1]

        # Verify tasks actually exist in DB
        all_tasks = tasks_store.list()
        assert len(all_tasks) == 2

    async def test_creates_events(self, tasks_store, events_store):
        items = {
            "tasks": [],
            "events": [
                {
                    "title": "Team meeting",
                    "start_time": "2025-12-25T14:00",
                    "end_time": "2025-12-25T15:00",
                    "frequency": "weekly",
                },
            ],
        }
        created = await apply_extracted_items(items, tasks_store, events_store)
        assert len(created) == 1
        assert "Team meeting" in created[0]
        assert "weekly" in created[0]

    async def test_skips_empty_titles(self, tasks_store, events_store):
        items = {
            "tasks": [{"title": "", "due_date": None}],
            "events": [{"title": "", "start_time": "2025-01-01T10:00"}],
        }
        created = await apply_extracted_items(items, tasks_store, events_store)
        assert len(created) == 0

    async def test_skips_events_without_start(self, tasks_store, events_store):
        items = {
            "tasks": [],
            "events": [{"title": "Something", "start_time": None}],
        }
        created = await apply_extracted_items(items, tasks_store, events_store)
        assert len(created) == 0

    async def test_mixed_tasks_and_events(self, tasks_store, events_store):
        items = {
            "tasks": [{"title": "Task A", "due_date": None}],
            "events": [{"title": "Event B", "start_time": "2025-06-01T09:00"}],
        }
        created = await apply_extracted_items(items, tasks_store, events_store)
        assert len(created) == 2
        assert any("Task A" in c for c in created)
        assert any("Event B" in c for c in created)
