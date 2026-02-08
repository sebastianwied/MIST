# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MIST is a local-first reflective AI companion. A central broker manages agent lifecycle and message routing. A Textual TUI provides the interface. All components talk to a local Ollama instance — no cloud dependencies.

## Architecture

```
TUI (mist-tui)                Desktop App (SwiftUI)
  │                              │
  │ Unix socket                  │ HTTP POST 127.0.0.1:8765
  ▼                              ▼
Broker (mist-broker)           FastAPI Server (server/app.py)
  │                              │
  ▼                              ▼
Agent (mist-agent)             Ollama
  │
  ▼
Ollama (local)
```

Four packages in one repo:

| Package | Path | Description |
|---------|------|-------------|
| `mist-core` | `core/` | Shared: storage, DB, settings, types, protocol, transport |
| `mist-broker` | `broker/` | Agent registry, message routing, Unix socket transport |
| `mist-tui` | `tui/` | Textual shell: layout, widget loading, editor screens, keybindings |
| `mist-agent` | `agent/` | MIST agent: persona, topics, notes, synthesis, aggregation, widgets |

Communication: TUI widgets each hold a `BrokerClient` (async Unix socket). The broker routes messages between TUI widgets and agents. Agents do not import TUI code and vice versa — all interaction is via the protocol.

## Prerequisites

- Python 3.13 with venv
- Ollama installed and running (`ollama serve`) with a model pulled (default `gemma3:1b`)
- Xcode 14.2+ (for desktop app only)

## Running the System

```bash
python3 -m venv env
source env/bin/activate

# Install all packages (editable)
pip install -e ./core -e ./broker -e ./agent -e ./tui

# Run in three terminals:
mist-broker          # 1. Start the broker
mist-agent           # 2. Start the agent
mist-tui             # 3. Start the TUI

# Legacy: plain REPL (no broker needed)
mist-repl

# Legacy: FastAPI server for desktop app
uvicorn server.app:app --host 127.0.0.1 --port 8765
```

## Running Tests

```bash
pytest tui/tests/ -v --ignore=tui/tests/test_integration.py
pytest broker/tests/ -v
pytest core/tests/ -v
pytest agent/tests/ -v
```

## Key Components

### mist-core (`core/src/mist_core/`)

| File | Purpose |
|------|---------|
| `storage.py` | JSONL persistence, topic index, note file helpers, topic merge, draft filing, path constants |
| `settings.py` | Settings load/save, model resolution chain |
| `protocol.py` | Message envelope, message types |
| `transport.py` | Async Unix socket client/server |
| `db.py` | SQLite connection and schema |
| `task_store.py` | SQLite-backed task CRUD |
| `event_store.py` | SQLite-backed event CRUD with recurrence |
| `ollama_client.py` | Ollama API wrapper with per-command model resolution |
| `types.py` | Shared type aliases (Writer, etc.) |

### mist-broker (`broker/src/mist_broker/`)

| File | Purpose |
|------|---------|
| `broker.py` | Main broker loop: accept connections, route messages |
| `registry.py` | Agent registration and lookup |
| `router.py` | Message dispatch between TUI clients and agents |
| `services.py` | Shared service handlers (tasks, events, storage) |
| `llm_service.py` | LLM request queuing to Ollama |

### mist-tui (`tui/src/mist_tui/`)

| File | Purpose |
|------|---------|
| `app.py` | `MistApp`: connects to broker, discovers agents, mounts widgets |
| `broker_client.py` | Async socket client for widget-to-broker communication |
| `widget_base.py` | `BrokerWidget` base class with `request_editor()` helper |
| `widget_loader.py` | Dynamic import of agent-declared widgets from manifests |
| `messages.py` | `EditorResult`, `RequestFullScreenEditor` message classes |
| `screens/editor_screen.py` | Full-screen editor with preview, F3 mode switch |
| `widgets/editor.py` | `SidePanelEditor` inline editor with F3 mode switch |
| `widgets/chat.py` | Built-in fallback chat panel |
| `widgets/notes.py` | Notes browser panel |
| `keybindings.py` | Global keybinding management |

### mist-agent (`agent/src/mist_agent/`)

| File | Purpose |
|------|---------|
| `agent.py` | Broker-connected agent: registers, handles commands and sub-commands |
| `manifest.py` | Agent metadata: name, capabilities, widget declarations |
| `commands.py` | Central command dispatcher |
| `notes.py` | Note/recall/note-new/note-list handlers |
| `aggregate.py` | LLM-based topic classification, routing, and topic merge |
| `synthesis.py` | Per-topic and global synthesis generation |
| `view_command.py` | `view`, `edit`, `save_edit` handlers |
| `respond.py` | Free-text LLM response handler |
| `prompts.py` | All LLM prompt templates |
| `persona_command.py` | Interactive persona editing via LLM |
| `extraction.py` | Task/event extraction from free text |
| `widgets/chat.py` | `MistChatPanel`: chat with persona editing, aggregate flow, editor integration |
| `widgets/topics.py` | `MistTopicsPanel`: topic browser |

## Editor System

Two editor modes, toggled with **F3**. The last-used mode persists within a session.

- **Full-screen** (`EditorScreen`): replaces the view, has live markdown preview (Ctrl+P)
- **Side-panel** (`SidePanelEditor`): inline beside the chat log

`view` opens read-only. `edit` opens read-write. `note new` creates a file and opens read-write.

Save flow (read-write): Ctrl+S → TUI sends content back to agent via broker sub-command (`edit:save` or `note:save`) → agent writes to disk.

## TUI Widget Loading

Agents declare widgets in their manifest. The TUI dynamically imports and mounts them:

1. TUI connects to broker, requests agent catalog
2. For each agent, parses widget specs from manifest
3. Imports widget classes, creates `BrokerClient` per widget
4. Mounts widgets as tabs in `TabbedContent`
5. Falls back to built-in `ChatPanel` if no widgets declared

## Data Flow

- **Input logging**: all input logged to `data/notes/rawLog.jsonl` as JSONL (`{time, source, text}`)
- **Aggregation**: `aggregate` classifies rawLog entries into topics via LLM, routes to `data/topics/<slug>/noteLog.jsonl`, archives to `data/notes/archive.jsonl`. `topic merge` combines two topics into one.
- **Notes**: `note new [topic] <title>` creates `.md` files in `data/topics/<slug>/notes/` or `data/notes/drafts/`
- **Synthesis**: `sync` generates per-topic synthesis; `resynth` does full rewrite. Global context at `data/synthesis/context.md`
- **Tasks/Events**: stored in `data/mist.db` (SQLite)

## Configuration

Config files in `data/config/` are gitignored and auto-created from defaults on first run.

- `persona.md` — agent personality
- `settings.json` — all settings including model selection
- `avatar.png` — optional desktop app avatar

Model resolution: `settings.model_<command>` → `settings.model` → built-in default (`gemma3:1b`).

## Broker Protocol

Messages are JSON objects, newline-delimited, over Unix domain sockets. See `ARCHITECTURE.md` for the full protocol spec including message types, shared service requests, and agent manifest format.

## Token Usage

Be mindful of token consumption. Prefer targeted file reads over broad exploration. Use Grep/Glob to locate what you need before reading full files. Avoid re-reading files already in context. When running tests, run only the relevant test suite rather than all four packages unless verifying a cross-cutting change.

## Future Direction

- **Desktop app → broker**: The macOS desktop app should connect to the broker (via TCP or WebSocket) instead of the legacy FastAPI server. Same protocol as the TUI.
- **Administrative model**: A lightweight always-running model (in the desktop app and default TUI) that sits above individual agents. It can see all agents registered with the broker, route user intent to the right agent, orchestrate multi-agent workflows, and provide a unified conversational interface without the user needing to know which agent handles what.

Sub-commands (colon-prefixed) are used for multi-step TUI flows that bypass normal dispatch:
- `persona:get`, `persona:draft`, `persona:save`
- `aggregate:classify`, `aggregate:route`
- `edit:save <name> <content>`
- `note:save <slug> <filename> <content>`
