"""Priority queue for LLM requests with configurable concurrency."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .client import OllamaClient

log = logging.getLogger(__name__)

# Priority levels
PRIORITY_ADMIN = 0
PRIORITY_AGENT = 1


@dataclass(order=True)
class _QueueItem:
    priority: int
    seq: int = field(compare=True)
    kwargs: dict[str, Any] = field(compare=False)
    future: asyncio.Future = field(compare=False)


class LLMQueue:
    """Async priority queue for LLM chat requests.

    Usage:
        queue = LLMQueue(client, max_concurrent=1)
        asyncio.create_task(queue.run())
        result = await queue.submit(prompt="hello", priority=PRIORITY_AGENT)
    """

    def __init__(self, client: OllamaClient, max_concurrent: int = 1) -> None:
        self._client = client
        self._queue: asyncio.PriorityQueue[_QueueItem] = asyncio.PriorityQueue()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._seq = 0
        self._running = False

    async def submit(
        self,
        prompt: str,
        priority: int = PRIORITY_AGENT,
        model: str | None = None,
        command: str | None = None,
        temperature: float = 0.3,
        system: str | None = None,
    ) -> str:
        """Enqueue an LLM request and return the result when ready."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._seq += 1
        item = _QueueItem(
            priority=priority,
            seq=self._seq,
            kwargs={
                "prompt": prompt,
                "model": model,
                "command": command,
                "temperature": temperature,
                "system": system,
            },
            future=future,
        )
        await self._queue.put(item)
        return await future

    async def run(self) -> None:
        """Process queue items. Run this as a background task."""
        self._running = True
        try:
            while self._running:
                item = await self._queue.get()
                asyncio.create_task(self._process(item))
        except asyncio.CancelledError:
            self._running = False

    async def _process(self, item: _QueueItem) -> None:
        async with self._semaphore:
            try:
                result = await asyncio.to_thread(
                    self._client.chat, **item.kwargs,
                )
                if not item.future.done():
                    item.future.set_result(result)
            except Exception as exc:
                if not item.future.done():
                    item.future.set_exception(exc)

    def stop(self) -> None:
        self._running = False
