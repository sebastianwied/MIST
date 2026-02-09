"""ManifestBuilder — fluent builder for agent manifests."""

from __future__ import annotations

from typing import Any


class ManifestBuilder:
    """Fluent builder for agent manifests.

    Usage:
        manifest = (ManifestBuilder("notes")
            .description("Note-taking and knowledge synthesis")
            .command("note", "Save a quick note", args={"text": "str"})
            .command("recall", "Recall notes on a topic")
            .panel("chat", "Notes", "chat", default=True)
            .panel("topics", "Topics", "browser")
            .build())
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._description = ""
        self._commands: list[dict[str, Any]] = []
        self._panels: list[dict[str, Any]] = []

    def description(self, desc: str) -> ManifestBuilder:
        self._description = desc
        return self

    def command(
        self,
        name: str,
        desc: str = "",
        args: dict[str, Any] | None = None,
    ) -> ManifestBuilder:
        cmd: dict[str, Any] = {"name": name, "description": desc}
        if args:
            cmd["args"] = args
        self._commands.append(cmd)
        return self

    def panel(
        self,
        id: str,
        label: str,
        type: str,
        default: bool = False,
    ) -> ManifestBuilder:
        p: dict[str, Any] = {"id": id, "label": label, "type": type}
        if default:
            p["default"] = True
        self._panels.append(p)
        return self

    def build(self) -> dict[str, Any]:
        return {
            "name": self._name,
            "description": self._description,
            "commands": self._commands,
            "panels": self._panels,
        }
