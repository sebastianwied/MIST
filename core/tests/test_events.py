"""Tests for mist_core.storage.events."""

from datetime import datetime, timedelta

import pytest

from mist_core.db import Database
from mist_core.storage.events import EventStore


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.connect()
    database.init_schema()
    yield database
    database.close()


@pytest.fixture
def events(db):
    return EventStore(db)


class TestEventCRUD:
    def test_create_and_get(self, events):
        eid = events.create("Meeting", start_time="2024-06-01T10:00")
        event = events.get(eid)
        assert event is not None
        assert event["title"] == "Meeting"

    def test_create_with_all_fields(self, events):
        eid = events.create(
            "Conference",
            start_time="2024-06-01T09:00",
            end_time="2024-06-01T17:00",
            location="Room 101",
            notes="Bring laptop",
        )
        event = events.get(eid)
        assert event["location"] == "Room 101"
        assert event["notes"] == "Bring laptop"

    def test_list(self, events):
        events.create("A", start_time="2024-06-01T10:00")
        events.create("B", start_time="2024-06-02T10:00")
        result = events.list()
        assert len(result) == 2

    def test_update(self, events):
        eid = events.create("Original", start_time="2024-06-01T10:00")
        events.update(eid, title="Updated")
        event = events.get(eid)
        assert event["title"] == "Updated"

    def test_delete(self, events):
        eid = events.create("To delete", start_time="2024-06-01T10:00")
        assert events.delete(eid)
        assert events.get(eid) is None

    def test_delete_nonexistent(self, events):
        assert not events.delete(999)


class TestRecurrence:
    def test_create_with_recurrence(self, events):
        eid = events.create(
            "Weekly standup",
            start_time="2024-06-03T09:00",
            frequency="weekly",
            interval=1,
        )
        event = events.get(eid)
        assert event["frequency"] == "weekly"
        assert event["rec_interval"] == 1

    def test_recurrence_deleted_with_event(self, events):
        eid = events.create(
            "Daily check",
            start_time="2024-06-01T09:00",
            frequency="daily",
        )
        events.delete(eid)
        assert events.get(eid) is None


class TestUpcoming:
    def test_upcoming_one_time_event(self, events):
        # Create event in the near future
        soon = (datetime.now() + timedelta(hours=1)).isoformat(timespec="minutes")
        events.create("Soon", start_time=soon)
        result = events.get_upcoming(days=1)
        assert len(result) == 1
        assert result[0]["title"] == "Soon"

    def test_upcoming_excludes_past(self, events):
        events.create("Past", start_time="2020-01-01T10:00")
        result = events.get_upcoming(days=7)
        assert len(result) == 0

    def test_upcoming_expands_recurring(self, events):
        # Weekly event starting now, should have multiple occurrences in 30 days
        now = datetime.now().isoformat(timespec="minutes")
        events.create("Weekly", start_time=now, frequency="weekly")
        result = events.get_upcoming(days=30)
        assert len(result) >= 4  # ~4 weeks in 30 days
