"""Tests for mist_core.storage.tasks."""

import pytest

from mist_core.db import Database
from mist_core.storage.tasks import TaskStore


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.connect()
    database.init_schema()
    yield database
    database.close()


@pytest.fixture
def tasks(db):
    return TaskStore(db)


class TestTaskCRUD:
    def test_create_and_get(self, tasks):
        tid = tasks.create("Buy groceries")
        task = tasks.get(tid)
        assert task is not None
        assert task["title"] == "Buy groceries"
        assert task["status"] == "todo"

    def test_create_with_due_date(self, tasks):
        tid = tasks.create("Submit paper", due_date="2024-12-31")
        task = tasks.get(tid)
        assert task["due_date"] == "2024-12-31"

    def test_list_only_open(self, tasks):
        tasks.create("Open task")
        tid2 = tasks.create("Done task")
        tasks.update(tid2, status="done")
        open_tasks = tasks.list()
        assert len(open_tasks) == 1
        assert open_tasks[0]["title"] == "Open task"

    def test_list_include_done(self, tasks):
        tasks.create("Open")
        tid2 = tasks.create("Done")
        tasks.update(tid2, status="done")
        all_tasks = tasks.list(include_done=True)
        assert len(all_tasks) == 2

    def test_update(self, tasks):
        tid = tasks.create("Original")
        tasks.update(tid, title="Updated")
        task = tasks.get(tid)
        assert task["title"] == "Updated"

    def test_delete(self, tasks):
        tid = tasks.create("To delete")
        assert tasks.delete(tid)
        assert tasks.get(tid) is None

    def test_delete_nonexistent(self, tasks):
        assert not tasks.delete(999)

    def test_get_nonexistent(self, tasks):
        assert tasks.get(999) is None


class TestTaskIdReuse:
    def test_reuses_completed_ids(self, tasks):
        tid1 = tasks.create("First")
        assert tid1 == 1
        tasks.update(tid1, status="done")
        tid2 = tasks.create("Second")
        assert tid2 == 1  # reuses id 1 since it's no longer 'todo'


class TestUpcoming:
    def test_upcoming_with_due_dates(self, tasks):
        tasks.create("Due soon", due_date="2020-01-01")
        tasks.create("Due later", due_date="2099-12-31")
        tasks.create("No date")
        upcoming = tasks.get_upcoming(days=365 * 100)
        assert len(upcoming) == 3

    def test_upcoming_excludes_far_future(self, tasks):
        tasks.create("Far future", due_date="2099-12-31")
        upcoming = tasks.get_upcoming(days=1)
        assert len(upcoming) == 0
