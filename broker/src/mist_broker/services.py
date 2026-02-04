"""Shared service dispatcher: tasks, events, storage, settings."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from mist_core.db import init_db
from mist_core.task_store import (
    create_task,
    delete_task,
    get_task,
    get_upcoming_tasks,
    list_tasks,
    update_task,
)
from mist_core.event_store import (
    create_event,
    delete_event,
    get_event,
    get_upcoming_events,
    list_events,
    update_event,
)
from mist_core.storage import (
    add_topic,
    append_to_archive,
    append_to_topic_notelog,
    clear_rawlog,
    find_topic,
    get_last_aggregate_time,
    get_last_sync_time,
    load_context,
    load_topic_about,
    load_topic_files,
    load_topic_index,
    load_topic_notelog,
    load_topic_synthesis,
    parse_all_entries,
    parse_rawlog,
    RawLogEntry,
    reset_topics,
    save_context,
    save_raw_input,
    save_topic_about,
    save_topic_synthesis,
    set_last_aggregate_time,
    set_last_sync_time,
    write_rawlog,
)
from mist_core.settings import (
    get_model,
    get_setting,
    is_valid_setting_key,
    load_settings,
    set_setting,
)
from mist_core.protocol import Message, MSG_SERVICE_RESPONSE, MSG_SERVICE_ERROR
from mist_core.transport import Connection

log = logging.getLogger(__name__)

BROKER_ID = "broker"


class ServiceDispatcher:
    """Dispatch service.request messages to the appropriate core API."""

    def initialize(self) -> None:
        """Ensure the database schema exists."""
        init_db()

    async def handle(self, msg: Message, conn: Connection) -> None:
        """Dispatch a service.request and send the result back."""
        payload = msg.payload
        service = payload.get("service")
        try:
            match service:
                case "tasks":
                    result = await self._handle_tasks(payload)
                case "events":
                    result = await self._handle_events(payload)
                case "storage":
                    result = await self._handle_storage(payload)
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
                return await asyncio.to_thread(list_tasks, **params)
            case "create":
                tid = await asyncio.to_thread(create_task, **params)
                return {"task_id": tid}
            case "get":
                return await asyncio.to_thread(get_task, **params)
            case "update":
                return await asyncio.to_thread(update_task, **params)
            case "delete":
                return await asyncio.to_thread(delete_task, **params)
            case "upcoming":
                return await asyncio.to_thread(get_upcoming_tasks, **params)
            case _:
                raise ValueError(f"unknown tasks action: {action}")

    # ── Events ───────────────────────────────────────────────────────

    async def _handle_events(self, payload: dict) -> Any:
        action = payload.get("action")
        params = payload.get("params", {})
        match action:
            case "list":
                return await asyncio.to_thread(list_events, **params)
            case "create":
                eid = await asyncio.to_thread(create_event, **params)
                return {"event_id": eid}
            case "get":
                return await asyncio.to_thread(get_event, **params)
            case "update":
                return await asyncio.to_thread(update_event, **params)
            case "delete":
                return await asyncio.to_thread(delete_event, **params)
            case "upcoming":
                return await asyncio.to_thread(get_upcoming_events, **params)
            case _:
                raise ValueError(f"unknown events action: {action}")

    # ── Storage ──────────────────────────────────────────────────────

    async def _handle_storage(self, payload: dict) -> Any:
        action = payload.get("action")
        params = payload.get("params", {})
        match action:
            case "save_raw_input":
                await asyncio.to_thread(save_raw_input, **params)
                return True
            case "load_context":
                return await asyncio.to_thread(load_context)
            case "save_context":
                await asyncio.to_thread(save_context, **params)
                return True
            case "load_topic_index":
                topics = await asyncio.to_thread(load_topic_index)
                return [asdict(t) for t in topics]
            case "load_topic_synthesis":
                return await asyncio.to_thread(load_topic_synthesis, **params)
            case "save_topic_synthesis":
                await asyncio.to_thread(save_topic_synthesis, **params)
                return True
            case "load_topic_notelog":
                entries = await asyncio.to_thread(load_topic_notelog, **params)
                return [asdict(e) for e in entries]
            case "append_to_topic_notelog":
                raw_entries = [
                    RawLogEntry(**e) for e in params.get("entries", [])
                ]
                slug = params["slug"]
                await asyncio.to_thread(
                    append_to_topic_notelog, slug, raw_entries,
                )
                return True
            case "add_topic":
                topic = await asyncio.to_thread(add_topic, **params)
                return asdict(topic)
            case "find_topic":
                topic = await asyncio.to_thread(find_topic, **params)
                return asdict(topic) if topic else None
            case "parse_rawlog":
                entries = await asyncio.to_thread(parse_rawlog)
                return [asdict(e) for e in entries]
            case "parse_all_entries":
                entries = await asyncio.to_thread(parse_all_entries)
                return [asdict(e) for e in entries]
            case "append_to_archive":
                raw_entries = [
                    RawLogEntry(**e) for e in params.get("entries", [])
                ]
                await asyncio.to_thread(append_to_archive, raw_entries)
                return True
            case "clear_rawlog":
                await asyncio.to_thread(clear_rawlog)
                return True
            case "write_rawlog":
                raw_entries = [
                    RawLogEntry(**e) for e in params.get("entries", [])
                ]
                await asyncio.to_thread(write_rawlog, raw_entries)
                return True
            case "load_topic_about":
                return await asyncio.to_thread(load_topic_about, **params)
            case "save_topic_about":
                await asyncio.to_thread(save_topic_about, **params)
                return True
            case "load_topic_files":
                return await asyncio.to_thread(load_topic_files)
            case "get_last_aggregate_time":
                return await asyncio.to_thread(get_last_aggregate_time)
            case "set_last_aggregate_time":
                await asyncio.to_thread(set_last_aggregate_time, **params)
                return True
            case "get_last_sync_time":
                return await asyncio.to_thread(get_last_sync_time)
            case "set_last_sync_time":
                await asyncio.to_thread(set_last_sync_time, **params)
                return True
            case "reset_topics":
                return await asyncio.to_thread(reset_topics)
            case _:
                raise ValueError(f"unknown storage action: {action}")

    # ── Settings ─────────────────────────────────────────────────────

    async def _handle_settings(self, payload: dict) -> Any:
        action = payload.get("action")
        params = payload.get("params", {})
        match action:
            case "get":
                return await asyncio.to_thread(get_setting, **params)
            case "set":
                await asyncio.to_thread(set_setting, **params)
                return True
            case "get_model":
                return await asyncio.to_thread(get_model, **params)
            case "load_all":
                return await asyncio.to_thread(load_settings)
            case "is_valid_key":
                return await asyncio.to_thread(is_valid_setting_key, **params)
            case _:
                raise ValueError(f"unknown settings action: {action}")
