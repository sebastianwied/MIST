"""AdminAgent — privileged, in-process default agent."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..protocol import (
    Message,
    MSG_COMMAND,
    MSG_RESPONSE,
    RESP_ERROR,
    RESP_LIST,
    RESP_TABLE,
    RESP_TEXT,
)
from ..llm.queue import LLMQueue, PRIORITY_ADMIN
from ..storage.settings import Settings
from .extraction import apply_extracted_items, extract_items
from .prompts import SYSTEM_PROMPT, USER_PROMPT

if TYPE_CHECKING:
    from ..broker.registry import AgentRegistry
    from ..broker.router import MessageRouter
    from ..broker.services import ServiceDispatcher
    from ..db import Database
    from ..paths import Paths

log = logging.getLogger(__name__)

ADMIN_MANIFEST = {
    "name": "admin",
    "description": "Default assistant",
    "commands": [
        {"name": "help", "description": "Show available commands"},
        {"name": "status", "description": "System status"},
        {"name": "agents", "description": "List connected agents"},
        {"name": "tasks", "description": "List tasks"},
        {"name": "events", "description": "List upcoming events"},
        {"name": "settings", "description": "Show settings"},
        {"name": "set", "description": "Change a setting"},
    ],
    "panels": [
        {"id": "chat", "label": "MIST", "type": "chat", "default": True},
    ],
}


class AdminAgent:
    """In-process privileged agent that routes and handles commands.

    Routing logic:
      1. ``@agent_name <text>`` → forward to named agent
      2. Command name matches a registered agent's manifest → forward
      3. Admin's own commands → handle locally
      4. Free text → LLM reflection + optional task/event extraction
    """

    def __init__(
        self,
        paths: Paths,
        db: Database,
        settings: Settings,
        llm_queue: LLMQueue,
        registry: AgentRegistry,
        services: ServiceDispatcher,
        router: MessageRouter,
    ) -> None:
        self._paths = paths
        self._db = db
        self._settings = settings
        self._llm_queue = llm_queue
        self._registry = registry
        self._services = services
        self._router = router
        self._agent_id: str | None = None

    @property
    def agent_id(self) -> str:
        if self._agent_id is None:
            raise RuntimeError("admin agent not registered")
        return self._agent_id

    def register(self) -> str:
        """Register with the broker as a privileged in-process agent."""
        entry = self._registry.register(
            conn=None, manifest=ADMIN_MANIFEST, privileged=True,
        )
        self._agent_id = entry.agent_id
        self._router.set_admin_handler(self.handle)
        log.info("admin agent registered as %s", self._agent_id)
        return self._agent_id

    async def handle(self, msg: Message) -> None:
        """Handle an incoming command message."""
        payload = msg.payload
        # v2 structured command payload: {"command": "...", "args": {...}, "text": "..."}
        command = payload.get("command", "")
        text = payload.get("text", "")
        args = payload.get("args", {})

        # If no structured command, treat the whole text as input
        if not command and text:
            command, _, remainder = text.partition(" ")
            command = command.lower()
            if not remainder:
                remainder = ""
            # Re-check if this is a known command, otherwise treat as free text
            if command not in self._own_commands() and not command.startswith("@"):
                # Not a command — treat the full text as free text
                await self._handle_free_text(msg, text)
                return
            text = remainder.strip()

        # 1. @agent mention → forward
        if command.startswith("@"):
            agent_name = command[1:]
            await self._route_by_mention(msg, agent_name, text)
            return

        # 2. External agent command → forward
        owner = self._registry.find_command_owner(command)
        if owner and owner.agent_id != self.agent_id:
            await self._router.forward_command(msg, owner.agent_id)
            return

        # 3. Admin's own commands
        match command:
            case "help":
                await self._handle_help(msg)
            case "status":
                await self._handle_status(msg)
            case "agents":
                await self._handle_agents(msg)
            case "tasks":
                await self._handle_tasks(msg, args)
            case "events":
                await self._handle_events(msg, args)
            case "settings":
                await self._handle_settings(msg)
            case "set":
                await self._handle_set(msg, args, text)
            case _:
                if text or command:
                    full_text = f"{command} {text}".strip() if command else text
                    await self._handle_free_text(msg, full_text)
                else:
                    await self._respond_error(msg, f"Unknown command: {command}")

    # ── Own command set ───────────────────────────────────────────────

    def _own_commands(self) -> set[str]:
        return {c["name"] for c in ADMIN_MANIFEST["commands"]}

    # ── Routing ───────────────────────────────────────────────────────

    async def _route_by_mention(
        self, msg: Message, agent_name: str, text: str,
    ) -> None:
        """Route ``@agent_name <text>`` to the named agent."""
        for entry in self._registry.all_agents():
            if entry.name == agent_name or entry.agent_id == agent_name:
                await self._router.forward_command(msg, entry.agent_id)
                return
        await self._respond_error(msg, f"No agent named '{agent_name}'")

    # ── Command handlers ──────────────────────────────────────────────

    async def _handle_help(self, msg: Message) -> None:
        lines = ["Available commands:"]
        lines.append("")

        # Admin commands
        lines.append("Admin:")
        for cmd in ADMIN_MANIFEST["commands"]:
            lines.append(f"  {cmd['name']:16s} {cmd['description']}")

        # External agent commands
        for entry in self._registry.all_agents():
            if entry.agent_id == self.agent_id:
                continue
            agent_cmds = entry.manifest.get("commands", [])
            if agent_cmds:
                lines.append("")
                lines.append(f"{entry.name} ({entry.agent_id}):")
                for cmd in agent_cmds:
                    name = cmd["name"] if isinstance(cmd, dict) else cmd
                    desc = cmd.get("description", "") if isinstance(cmd, dict) else ""
                    lines.append(f"  {name:16s} {desc}")

        lines.append("")
        lines.append("Use @agent_name <text> to send directly to an agent.")

        await self._respond_text(msg, "\n".join(lines))

    async def _handle_status(self, msg: Message) -> None:
        agents = self._registry.all_agents()
        tasks = await asyncio.to_thread(self._services._tasks.list)
        events = await asyncio.to_thread(self._services._events.get_upcoming, days=7)

        lines = [
            f"Agents: {len(agents)} connected",
            f"Tasks:  {len(tasks)} open",
            f"Events: {len(events)} upcoming (7d)",
        ]
        await self._respond_text(msg, "\n".join(lines))

    async def _handle_agents(self, msg: Message) -> None:
        agents = self._registry.all_agents()
        if not agents:
            await self._respond_text(msg, "No agents connected.")
            return

        items = []
        for entry in agents:
            priv = " (privileged)" if entry.privileged else ""
            conn = "in-process" if entry.conn is None else "connected"
            items.append(f"{entry.agent_id}: {entry.name}{priv} [{conn}]")

        await self._respond_list(msg, items, title="Connected Agents")

    async def _handle_tasks(self, msg: Message, args: dict) -> None:
        include_done = args.get("all", False)
        tasks = await asyncio.to_thread(self._services._tasks.list, include_done=include_done)
        if not tasks:
            await self._respond_text(msg, "No tasks.")
            return

        columns = ["ID", "Title", "Status", "Due"]
        rows = []
        for t in tasks:
            rows.append([
                str(t["id"]),
                t["title"],
                t["status"],
                t.get("due_date") or "",
            ])
        await self._respond_table(msg, columns, rows, title="Tasks")

    async def _handle_events(self, msg: Message, args: dict) -> None:
        days = args.get("days", 7)
        events = await asyncio.to_thread(self._services._events.get_upcoming, days=days)
        if not events:
            await self._respond_text(msg, "No upcoming events.")
            return

        columns = ["ID", "Title", "Start", "Frequency"]
        rows = []
        for e in events:
            rows.append([
                str(e.get("id", "")),
                e["title"],
                e["start_time"],
                e.get("frequency") or "",
            ])
        await self._respond_table(msg, columns, rows, title="Upcoming Events")

    async def _handle_settings(self, msg: Message) -> None:
        all_settings = await asyncio.to_thread(self._settings.load)
        if not all_settings:
            await self._respond_text(msg, "No settings configured.")
            return

        lines = ["Current settings:"]
        for k, v in sorted(all_settings.items()):
            lines.append(f"  {k} = {v}")
        await self._respond_text(msg, "\n".join(lines))

    async def _handle_set(self, msg: Message, args: dict, text: str) -> None:
        key = args.get("key", "")
        value = args.get("value", "")

        # Fall back to parsing from text: "set key value"
        if not key and text:
            parts = text.split(None, 1)
            if len(parts) >= 2:
                key, value = parts[0], parts[1]
            elif len(parts) == 1:
                await self._respond_error(msg, "Usage: set <key> <value>")
                return

        if not key:
            await self._respond_error(msg, "Usage: set <key> <value>")
            return

        # Coerce numeric values
        try:
            value = int(value)
        except (ValueError, TypeError):
            pass

        if not Settings.is_valid_key(key):
            await self._respond_text(
                msg, f"Warning: '{key}' is not a recognised setting key.",
            )

        await asyncio.to_thread(self._settings.set, key=key, value=value)
        await self._respond_text(msg, f"Setting '{key}' set to '{value}'.")

    # ── Free text ─────────────────────────────────────────────────────

    async def _handle_free_text(self, msg: Message, text: str) -> None:
        """Reflect on free text via LLM, optionally extract tasks/events."""
        persona = self._load_persona()
        context = ""
        user_profile = ""

        system = SYSTEM_PROMPT.format(
            persona=persona, user_profile=user_profile, context=context,
        )
        prompt = USER_PROMPT.format(text=text)

        try:
            response = await self._llm_queue.submit(
                prompt=prompt,
                system=system,
                priority=PRIORITY_ADMIN,
                command="reflect",
            )
        except Exception:
            log.exception("LLM reflection failed")
            await self._respond_error(msg, "LLM request failed")
            return

        await self._respond_text(msg, response)

        # Optional extraction
        agency_mode = await asyncio.to_thread(self._settings.get, key="agency_mode")
        if agency_mode and agency_mode != "off":
            items = await extract_items(text, self._llm_queue)
            has_items = items.get("tasks") or items.get("events")
            if has_items:
                created = await apply_extracted_items(
                    items, self._services._tasks, self._services._events,
                )
                if created:
                    summary = "\n".join(created)
                    await self._respond_text(msg, f"Auto-extracted:\n{summary}")

    def _load_persona(self) -> str:
        """Load the admin persona from disk."""
        path = self._paths.agent_dir(self.agent_id) / "config" / "persona.md"
        if path.exists():
            return path.read_text().strip()
        return "You are MIST, a personal information and knowledge assistant."

    # ── Response helpers ──────────────────────────────────────────────

    async def _respond_text(
        self, msg: Message, text: str, fmt: str = "plain",
    ) -> None:
        response = Message.reply(msg, self.agent_id, MSG_RESPONSE, {
            "type": RESP_TEXT,
            "content": {"text": text, "format": fmt},
        })
        await self._router.deliver_response(response)

    async def _respond_table(
        self, msg: Message, columns: list[str], rows: list[list],
        title: str = "",
    ) -> None:
        response = Message.reply(msg, self.agent_id, MSG_RESPONSE, {
            "type": RESP_TABLE,
            "content": {"columns": columns, "rows": rows, "title": title},
        })
        await self._router.deliver_response(response)

    async def _respond_list(
        self, msg: Message, items: list[str], title: str = "",
    ) -> None:
        response = Message.reply(msg, self.agent_id, MSG_RESPONSE, {
            "type": RESP_LIST,
            "content": {"items": items, "title": title},
        })
        await self._router.deliver_response(response)

    async def _respond_error(self, msg: Message, error: str) -> None:
        response = Message.reply(msg, self.agent_id, MSG_RESPONSE, {
            "type": RESP_ERROR,
            "content": {"message": error},
        })
        await self._router.deliver_response(response)
