# MIST v2 Architecture

## Overview

MIST is a personal AI assistant with a modular agent architecture. A single Python process runs the **Core** (services, broker, admin agent). External agents connect over **Unix sockets** using the `mist-client` library. A **Tauri UI** connects over **WebSocket**.

```
┌──────────────────────────────────────────────────┐
│  Core Process (Python)                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │ Services  │  │  Broker  │  │ Admin Agent  │   │
│  │ storage   │  │  router  │  │ (privileged) │   │
│  │ settings  │  │ registry │  │              │   │
│  │ llm queue │  │          │  │              │   │
│  └──────────┘  └──────────┘  └──────────────┘   │
│       ▲             ▲               ▲            │
└───────┼─────────────┼───────────────┼────────────┘
        │        WebSocket            │
   agent client   Tauri UI      direct access
   lib requests
        │
   Unix sockets
   ┌────┴──────────────┐
   │ Notes │  Science  │
   │ Agent │  Agent    │
   └───────┘  └────────┘
```

## Packages

| Package | Path | Depends On | Purpose |
|---------|------|------------|---------|
| `mist-core` | `core/` | `ollama`, `websockets` | Core process: services, broker, admin agent, transport |
| `mist-client` | `client/` | *(none)* | Standalone agent SDK — agents import only this |
| `notes-agent` | `agents/notes/` | `mist-client` | Note-taking, topic management, synthesis |
| `science-agent` | `agents/science/` | `mist-client` | arXiv/Semantic Scholar search, article library |

## Key Design Decisions

### 1. Agents never import core

External agents depend solely on `mist-client`, a standalone library with its own vendored copy of the protocol. This decouples agent development from core internals and makes agents independently distributable.

### 2. All responses are structured JSON

Every response has a `type` field. The UI renders components based on type rather than parsing free text.

| Type | Content | Purpose |
|------|---------|---------|
| `text` | `{text, format}` | Chat messages |
| `table` | `{columns, rows, title}` | Search results, task lists |
| `list` | `{items, title}` | Topics, tags |
| `editor` | `{content, title, path, read_only}` | Document viewer/editor |
| `confirm` | `{prompt, options, context}` | User decisions |
| `progress` | `{message, percent}` | Activity indicators |
| `error` | `{message, code, details}` | Error display |

### 3. Namespaced storage

The broker injects `agent_id` into every service request. Each agent gets its own directory at `data/agents/<agent_id>/` for notes, topics, and config. Shared resources (tasks, events, articles, settings) live in a global SQLite database.

### 4. Queued LLM requests

A priority queue manages all LLM calls. Admin requests run at priority 0, agent requests at priority 1. Configurable concurrency (default: 1). Each `submit()` returns an async future.

### 5. Admin agent is privileged

The admin agent runs in-process with direct access to the registry, storage, and LLM queue. It routes commands to external agents by matching `@agent` mentions or command names against agent manifests.

## Protocol

### Message Envelope

```python
@dataclass(frozen=True)
class Message:
    type: str        # Message type constant
    id: str          # UUID
    sender: str      # Agent ID or "ui"
    to: str          # Target agent ID or "broker"
    payload: dict    # Type-specific data
    reply_to: str | None = None
    timestamp: str | None = None  # ISO 8601, auto-set
```

### Message Types

- **Lifecycle**: `agent.register`, `agent.ready`, `agent.disconnect`, `agent.list`, `agent.catalog`
- **Commands**: `command` (with structured payload), `response` (with typed content)
- **Services**: `service.request`, `service.response`, `service.error`
- **Inter-agent**: `agent.message`, `agent.broadcast`

### Agent Manifests

Agents declare capabilities via manifests:

```python
{
    "name": "notes",
    "description": "Note-taking and knowledge synthesis",
    "commands": [
        {"name": "note", "description": "Save a quick note", "args": {...}},
    ],
    "panels": [
        {"id": "chat", "label": "Notes", "type": "chat", "default": True},
    ],
}
```

Panel types: `chat`, `browser`, `editor`, `custom`.

## Core Internals

### Storage Layer (`core/src/mist_core/storage/`)

- **NoteStorage** — per-agent note buffers, topics, feeds, synthesis, drafts
- **TaskStore** — SQLite-backed tasks with CRUD and upcoming filter
- **EventStore** — SQLite-backed events with recurrence expansion
- **ArticleStore** — SQLite-backed articles with tags
- **Settings** — JSON config with model resolution chain
- **Logs** — JSONL helpers (LogEntry, parse/append/write)

### Broker (`core/src/mist_core/broker/`)

- **AgentRegistry** — tracks connected agents, manifests, privileged flag
- **MessageRouter** — routes messages between agents, admin, and UI
- **ServiceDispatcher** — handles `service.request` messages, injects agent namespace

### LLM (`core/src/mist_core/llm/`)

- **OllamaClient** — sync and async chat with Ollama
- **LLMQueue** — priority queue with configurable concurrency

### Transport (`core/src/mist_core/transport.py`)

- Unix socket server for agent connections
- WebSocket server for UI connections
- Shared `Connection` abstraction

### Paths (`core/src/mist_core/paths.py`)

All path constants parameterized by a root directory. Enables test isolation via `Paths(tmp_path)`.

## Data Layout

```
data/
├── mist.db                  # Shared SQLite (tasks, events, articles)
├── config/
│   └── settings.json
├── broker/
│   └── mist.sock
└── agents/
    ├── admin/
    ├── notes-0/
    │   ├── config/persona.md
    │   ├── notes/
    │   │   ├── noteBuffer.jsonl
    │   │   └── drafts/
    │   └── topics/
    │       ├── index.json
    │       └── <slug>/
    └── science-0/
        └── config/persona.md
```

## Build Order

| Phase | Deliverable |
|-------|-------------|
| 1 | Protocol, paths, DB, storage, transport |
| 2 | Broker, services, LLM queue, main entry point |
| 3 | Agent client library (`mist-client`) |
| 4 | Admin agent |
| 5 | Notes agent |
| 6 | Science agent |
| 7 | Tauri UI |

## Running

```bash
# Install core (editable)
cd core && pip install -e .

# Start core process
python -m mist_core

# Install and run an agent (separate terminal)
cd agents/notes && pip install -e .
python -m notes_agent
```

## Testing

```bash
# Per-package
cd core && pytest tests/ -v
cd client && pytest tests/ -v
cd agents/notes && pytest tests/ -v
cd agents/science && pytest tests/ -v
```

Test isolation: all classes accept a `Paths` instance parameterized by `tmp_path`. No monkeypatching needed.
