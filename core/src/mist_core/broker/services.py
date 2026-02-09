"""Service dispatcher: routes service.request messages to storage classes."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from ..db import Database
from ..paths import Paths
from ..protocol import Message, MSG_SERVICE_RESPONSE, MSG_SERVICE_ERROR
from ..storage.articles import ArticleStore
from ..storage.events import EventStore
from ..storage.logs import LogEntry
from ..storage.notes import NoteStorage
from ..storage.settings import Settings
from ..storage.tasks import TaskStore
from ..transport import Connection, WebSocketConnection

log = logging.getLogger(__name__)

BROKER_ID = "broker"


class ServiceDispatcher:
    """Dispatch service.request messages to class-based stores.

    Storage requests are namespaced: the broker looks up the requesting
    agent's ID from the registry and injects it into NoteStorage calls.
    """

    def __init__(
        self,
        paths: Paths,
        db: Database,
        settings: Settings,
    ) -> None:
        self._paths = paths
        self._db = db
        self._settings = settings
        self._tasks = TaskStore(db)
        self._events = EventStore(db)
        self._articles = ArticleStore(db)
        self._note_stores: dict[str, NoteStorage] = {}

    def _get_note_storage(self, agent_id: str) -> NoteStorage:
        """Lazy-create a NoteStorage scoped to *agent_id*."""
        if agent_id not in self._note_stores:
            self._paths.ensure_agent_dirs(agent_id)
            self._note_stores[agent_id] = NoteStorage(self._paths, agent_id)
        return self._note_stores[agent_id]

    async def handle(
        self,
        msg: Message,
        conn: Connection | WebSocketConnection,
        agent_id: str | None = None,
    ) -> None:
        """Dispatch a service.request and send the result back."""
        payload = msg.payload
        service = payload.get("service")
        # Use explicit agent_id or fall back to msg.sender
        aid = agent_id or msg.sender
        try:
            match service:
                case "tasks":
                    result = await self._handle_tasks(payload)
                case "events":
                    result = await self._handle_events(payload)
                case "articles":
                    result = await self._handle_articles(payload)
                case "storage":
                    result = await self._handle_storage(payload, aid)
                case "settings":
                    result = await self._handle_settings(payload)
                case _:
                    raise ValueError(f"unknown service: {service}")
            reply = Message.reply(
                msg, BROKER_ID, MSG_SERVICE_RESPONSE, {"result": result},
            )
        except Exception as exc:
            log.exception("service error: %s", exc)
            reply = Message.reply(
                msg, BROKER_ID, MSG_SERVICE_ERROR, {"error": str(exc)},
            )
        await conn.send(reply)

    # ── Tasks ────────────────────────────────────────────────────────

    async def _handle_tasks(self, payload: dict) -> Any:
        action = payload.get("action")
        params = payload.get("params", {})
        match action:
            case "list":
                return await asyncio.to_thread(self._tasks.list, **params)
            case "create":
                tid = await asyncio.to_thread(self._tasks.create, **params)
                return {"task_id": tid}
            case "get":
                return await asyncio.to_thread(self._tasks.get, **params)
            case "update":
                return await asyncio.to_thread(self._tasks.update, **params)
            case "delete":
                return await asyncio.to_thread(self._tasks.delete, **params)
            case "upcoming":
                return await asyncio.to_thread(self._tasks.get_upcoming, **params)
            case _:
                raise ValueError(f"unknown tasks action: {action}")

    # ── Events ───────────────────────────────────────────────────────

    async def _handle_events(self, payload: dict) -> Any:
        action = payload.get("action")
        params = payload.get("params", {})
        match action:
            case "list":
                return await asyncio.to_thread(self._events.list, **params)
            case "create":
                eid = await asyncio.to_thread(self._events.create, **params)
                return {"event_id": eid}
            case "get":
                return await asyncio.to_thread(self._events.get, **params)
            case "update":
                return await asyncio.to_thread(self._events.update, **params)
            case "delete":
                return await asyncio.to_thread(self._events.delete, **params)
            case "upcoming":
                return await asyncio.to_thread(self._events.get_upcoming, **params)
            case _:
                raise ValueError(f"unknown events action: {action}")

    # ── Articles ─────────────────────────────────────────────────────

    async def _handle_articles(self, payload: dict) -> Any:
        action = payload.get("action")
        params = payload.get("params", {})
        match action:
            case "list":
                return await asyncio.to_thread(self._articles.list, **params)
            case "create":
                aid = await asyncio.to_thread(self._articles.create, **params)
                return {"article_id": aid}
            case "get":
                return await asyncio.to_thread(self._articles.get, **params)
            case "update":
                return await asyncio.to_thread(self._articles.update, **params)
            case "delete":
                return await asyncio.to_thread(self._articles.delete, **params)
            case "add_tag":
                await asyncio.to_thread(self._articles.add_tag, **params)
                return True
            case "remove_tag":
                await asyncio.to_thread(self._articles.remove_tag, **params)
                return True
            case "list_tags":
                return await asyncio.to_thread(self._articles.list_tags)
            case _:
                raise ValueError(f"unknown articles action: {action}")

    # ── Storage (namespaced by agent_id) ─────────────────────────────

    async def _handle_storage(self, payload: dict, agent_id: str) -> Any:
        action = payload.get("action")
        params = payload.get("params", {})
        ns = self._get_note_storage(agent_id)
        match action:
            case "save_raw_input":
                await asyncio.to_thread(ns.save_raw_input, **params)
                return True
            case "parse_buffer":
                entries = await asyncio.to_thread(ns.parse_buffer)
                return [asdict(e) for e in entries]
            case "clear_buffer":
                await asyncio.to_thread(ns.clear_buffer)
                return True
            case "write_buffer":
                raw = [LogEntry(**e) for e in params.get("entries", [])]
                await asyncio.to_thread(ns.write_buffer, raw)
                return True
            case "load_topic_index":
                topics = await asyncio.to_thread(ns.load_topic_index)
                return [asdict(t) for t in topics]
            case "add_topic":
                topic = await asyncio.to_thread(ns.add_topic, **params)
                return asdict(topic)
            case "find_topic":
                topic = await asyncio.to_thread(ns.find_topic, **params)
                return asdict(topic) if topic else None
            case "load_topic_buffer":
                entries = await asyncio.to_thread(ns.load_topic_buffer, **params)
                return [asdict(e) for e in entries]
            case "append_to_topic_buffer":
                raw = [LogEntry(**e) for e in params.get("entries", [])]
                slug = params["slug"]
                await asyncio.to_thread(ns.append_to_topic_buffer, slug, raw)
                return True
            case "load_topic_note_feed":
                return await asyncio.to_thread(ns.load_topic_note_feed, **params)
            case "save_topic_note_feed":
                await asyncio.to_thread(ns.save_topic_note_feed, **params)
                return True
            case "load_topic_synthesis":
                return await asyncio.to_thread(ns.load_topic_synthesis, **params)
            case "save_topic_synthesis":
                await asyncio.to_thread(ns.save_topic_synthesis, **params)
                return True
            case "list_drafts":
                return await asyncio.to_thread(ns.list_drafts)
            case "load_draft":
                return await asyncio.to_thread(ns.load_draft, **params)
            case "save_draft":
                await asyncio.to_thread(ns.save_draft, **params)
                return True
            case "create_draft":
                filename, _ = await asyncio.to_thread(ns.create_draft, **params)
                return {"filename": filename}
            case "list_topic_notes":
                return await asyncio.to_thread(ns.list_topic_notes, **params)
            case "load_topic_note":
                return await asyncio.to_thread(ns.load_topic_note, **params)
            case "save_topic_note":
                await asyncio.to_thread(ns.save_topic_note, **params)
                return True
            case "create_topic_note":
                filename, _ = await asyncio.to_thread(ns.create_topic_note, **params)
                return {"filename": filename}
            case "merge_topics":
                count = await asyncio.to_thread(ns.merge_topics, **params)
                return {"entries_moved": count}
            case "get_last_aggregate_time":
                return await asyncio.to_thread(ns.get_last_aggregate_time)
            case "set_last_aggregate_time":
                await asyncio.to_thread(ns.set_last_aggregate_time, **params)
                return True
            case "get_last_sync_time":
                return await asyncio.to_thread(ns.get_last_sync_time)
            case "set_last_sync_time":
                await asyncio.to_thread(ns.set_last_sync_time, **params)
                return True
            case _:
                raise ValueError(f"unknown storage action: {action}")

    # ── Settings ─────────────────────────────────────────────────────

    async def _handle_settings(self, payload: dict) -> Any:
        action = payload.get("action")
        params = payload.get("params", {})
        match action:
            case "get":
                return await asyncio.to_thread(self._settings.get, **params)
            case "set":
                await asyncio.to_thread(self._settings.set, **params)
                return True
            case "get_model":
                return await asyncio.to_thread(self._settings.get_model, **params)
            case "load_all":
                return await asyncio.to_thread(self._settings.load)
            case "is_valid_key":
                return Settings.is_valid_key(**params)
            case _:
                raise ValueError(f"unknown settings action: {action}")
