"""Tests for mist_core.llm.queue."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from mist_core.llm.queue import LLMQueue, PRIORITY_ADMIN, PRIORITY_AGENT
from mist_core.llm.client import OllamaClient
from mist_core.storage.settings import Settings
from mist_core.paths import Paths


@pytest.fixture
def mock_client():
    client = MagicMock(spec=OllamaClient)
    client.chat = MagicMock(return_value="LLM response")
    return client


@pytest.fixture
def queue(mock_client):
    return LLMQueue(mock_client, max_concurrent=1)


class TestLLMQueue:
    async def test_submit_returns_result(self, queue, mock_client):
        task = asyncio.create_task(queue.run())
        try:
            result = await asyncio.wait_for(
                queue.submit(prompt="hello", priority=PRIORITY_AGENT),
                timeout=2.0,
            )
            assert result == "LLM response"
            mock_client.chat.assert_called_once()
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_priority_ordering(self, mock_client):
        """Admin requests should be processed before agent requests."""
        call_order = []
        original_chat = mock_client.chat

        def tracking_chat(**kwargs):
            call_order.append(kwargs["prompt"])
            return f"reply to {kwargs['prompt']}"

        mock_client.chat = tracking_chat

        # Use concurrency=1 so requests queue up
        queue = LLMQueue(mock_client, max_concurrent=1)

        # Block the queue with a slow item first
        blocker = asyncio.Event()
        original_side = mock_client.chat

        first_call = True

        def blocking_chat(**kwargs):
            nonlocal first_call
            if first_call:
                first_call = False
                # Simulate slow processing
                import time
                time.sleep(0.05)
            call_order.append(kwargs["prompt"])
            return f"reply to {kwargs['prompt']}"

        mock_client.chat = blocking_chat
        task = asyncio.create_task(queue.run())

        try:
            # Submit in reverse priority order: agent first, then admin
            # But since concurrency=1, they'll queue up
            f_agent = asyncio.ensure_future(
                queue.submit(prompt="agent-req", priority=PRIORITY_AGENT)
            )
            # Small delay to ensure ordering
            await asyncio.sleep(0.01)
            f_admin = asyncio.ensure_future(
                queue.submit(prompt="admin-req", priority=PRIORITY_ADMIN)
            )

            await asyncio.wait_for(
                asyncio.gather(f_agent, f_admin),
                timeout=5.0,
            )

            # Both should complete
            assert f_agent.done()
            assert f_admin.done()
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_error_propagated(self, mock_client):
        mock_client.chat = MagicMock(side_effect=RuntimeError("ollama down"))
        queue = LLMQueue(mock_client, max_concurrent=1)
        task = asyncio.create_task(queue.run())
        try:
            with pytest.raises(RuntimeError, match="ollama down"):
                await asyncio.wait_for(
                    queue.submit(prompt="hello"),
                    timeout=2.0,
                )
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_multiple_concurrent(self, mock_client):
        """With max_concurrent=2, two requests can run simultaneously."""
        mock_client.chat = MagicMock(return_value="ok")
        queue = LLMQueue(mock_client, max_concurrent=2)
        task = asyncio.create_task(queue.run())
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    queue.submit(prompt="a"),
                    queue.submit(prompt="b"),
                ),
                timeout=2.0,
            )
            assert results == ["ok", "ok"]
            assert mock_client.chat.call_count == 2
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
