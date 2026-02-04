# MIST Architecture

## Overview

MIST is a local-first multi-agent system. A central **broker** manages agent lifecycle, message routing, shared services, and LLM access. **Agents** are independent packages with their own logic, data, and UI widgets. A **TUI** (Textual) provides the interface by mounting agent-provided widgets. All communication happens over Unix domain sockets using a JSON-line protocol.

```
┌─────────────────────────────────────────────────────────┐
│                      TUI (mist-tui)                     │
│                                                         │
│  Layout shell: mounts agent widgets, manages focus,     │
│  keybindings, and UI state. Does not route agent        │
│  messages — widgets talk to the broker directly.        │
│                                                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │ MIST chat  │  │ MIST topics│  │ AgentB     │        │
│  │ widget     │  │ widget     │  │ widget     │  ...    │
│  │ (broker ←→)│  │ (broker ←→)│  │ (broker ←→)│        │
│  └────────────┘  └────────────┘  └────────────┘        │
└─────────────────────────────────────────────────────────┘
        │                 │                │
   Unix sockets (each widget holds its own broker client)
        │                 │                │
        ▼                 ▼                ▼
┌─────────────────────────────────────────────────────────┐
│                    Broker (mist-broker)                  │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │Transport │  │Agent Registry│  │ Message Router    │  │
│  │(Unix sock│  │(lifecycle,   │  │ (dispatch, relay, │  │
│  │ + TCP    │  │ discovery)   │  │  inter-agent)     │  │
│  │ later)   │  │              │  │                   │  │
│  └──────────┘  └──────────────┘  └──────────────────┘  │
│                                                         │
│  ┌──────────────────┐  ┌────────────────────────────┐   │
│  │ Shared Services  │  │ LLM Service                │   │
│  │ (tasks, events,  │  │ (queues requests to Ollama,│   │
│  │  storage, DB)    │  │  prioritizes, rate-limits) │   │
│  └──────────────────┘  └────────────────────────────┘   │
│                                                         │
│              Unix socket per agent                       │
└──────┬──────────────────┬──────────────────┬────────────┘
       │                  │                  │
       ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  MIST Agent  │  │  Agent B     │  │  Agent C     │
│  (mist-agent)│  │              │  │              │
│              │  │              │  │              │
│  - persona   │  │  - own logic │  │  - own logic │
│  - topics    │  │  - own data  │  │  - own data  │
│  - synthesis │  │  - widgets/  │  │  - widgets/  │
│  - notes     │  │              │  │              │
│  - widgets/  │  │              │  │              │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Design Decisions

1. **Strict message-based data access.** Agents do not import shared infrastructure directly. All access to tasks, events, storage, and LLM goes through the broker via messages. This enforces isolation and lets the broker control permissions.

2. **Widgets hold direct broker connections.** Agent-provided Textual widgets each hold their own broker client. The TUI mounts widgets but does not route agent messages — it only manages layout, focus, and keybindings.

3. **Broker mediates LLM access.** Agents request inference through the broker, which queues and prioritizes requests to Ollama. This prevents resource contention when multiple agents are active.

4. **Unix domain sockets.** Local communication uses Unix sockets. The protocol is transport-agnostic (JSON lines with a message envelope) so the broker can later also listen on TCP for remote access.

5. **Agents ship Textual widgets.** Each agent package includes a `widgets/` directory with Textual widget classes. The TUI dynamically imports and mounts them based on agent registration.

6. **Same repo, separate packages.** All packages live in one repository. No external network connections unless explicitly configured.

## Packages

| Package | Description |
|---------|-------------|
| `mist-core` | Shared infrastructure: storage, DB, task/event stores, settings, protocol definitions, types |
| `mist-broker` | Agent lifecycle, message routing, shared service access, LLM service, transport layer |
| `mist-tui` | Textual shell: layout, widget loading, UI state, keybindings |
| `mist-agent` | MIST agent: persona, topics, synthesis, aggregation, notes, prompts, widgets |

## Protocol

All messages are JSON objects, newline-delimited, over Unix domain sockets.

### Message Envelope

```json
{
  "type": "message.type",
  "from": "sender-id",
  "to": "recipient-id",
  "id": "uuid",
  "reply_to": "uuid or null",
  "payload": {}
}
```

### Message Types

#### Lifecycle

| Type | Direction | Purpose |
|------|-----------|---------|
| `agent.register` | Agent → Broker | Register agent, declare capabilities and widgets |
| `agent.ready` | Broker → Agent | Registration confirmed, assigned agent ID |
| `agent.disconnect` | Agent → Broker | Graceful shutdown |
| `agent.list` | TUI → Broker | Request list of registered agents |
| `agent.catalog` | Broker → TUI | List of agents with their widget manifests |

#### Commands and Responses

| Type | Direction | Purpose |
|------|-----------|---------|
| `command` | Widget → Broker → Agent | User command or free-text input |
| `response` | Agent → Broker → Widget | Complete response (non-streaming) |
| `response.chunk` | Agent → Broker → Widget | Streaming partial response |
| `response.end` | Agent → Broker → Widget | Stream complete |

#### Shared Services

| Type | Direction | Purpose |
|------|-----------|---------|
| `service.request` | Agent → Broker | Access shared service (tasks, events, storage, LLM) |
| `service.response` | Broker → Agent | Service result |
| `service.error` | Broker → Agent | Service request failed |

#### Widget Declarations

| Type | Direction | Purpose |
|------|-----------|---------|
| `widget.declare` | Agent → Broker → TUI | Agent declares available Textual widgets |
| `widget.update` | Agent → Broker → Widget | Agent pushes state update to a widget |

### Shared Service Requests

Agents access shared infrastructure by sending `service.request` messages to the broker.

**Tasks:**
```json
{"service": "tasks", "action": "list", "params": {"include_done": false}}
{"service": "tasks", "action": "create", "params": {"title": "...", "due_date": "..."}}
{"service": "tasks", "action": "update", "params": {"task_id": 1, "status": "done"}}
{"service": "tasks", "action": "delete", "params": {"task_id": 1}}
```

**Events:**
```json
{"service": "events", "action": "list", "params": {}}
{"service": "events", "action": "create", "params": {"title": "...", "start_time": "..."}}
```

**Storage (per-agent scoped):**
```json
{"service": "storage", "action": "save_raw_input", "params": {"text": "...", "source": "terminal"}}
{"service": "storage", "action": "load_context", "params": {}}
```

**LLM:**
```json
{"service": "llm", "action": "chat", "params": {"prompt": "...", "system": "...", "model": "gemma3:1b", "temperature": 0.3, "stream": true}}
```

## Agent Structure

Each agent is a Python package with this structure:

```
mist-agent/
├── pyproject.toml
└── src/mist_agent/
    ├── __init__.py
    ├── agent.py            # Agent main: connects to broker, handles messages
    ├── manifest.py         # Agent metadata: name, commands, widget list
    ├── logic/
    │   ├── respond.py      # Free-text handler
    │   ├── aggregate.py    # Topic classification
    │   ├── synthesis.py    # Synthesis generation
    │   ├── notes.py        # Note/recall
    │   ├── extraction.py   # Task/event extraction
    │   └── prompts.py      # LLM prompt templates
    ├── config/
    │   ├── persona.py      # Persona loading
    │   └── profile.py      # User profile loading
    └── widgets/
        ├── __init__.py     # Widget manifest
        ├── chat.py         # ChatPanel(Widget) — main chat interface
        └── topics.py       # TopicsPanel(Widget) — topic browser
```

### Agent Manifest

Each agent declares itself via a manifest:

```python
MANIFEST = {
    "name": "MIST",
    "description": "Reflective journaling companion",
    "commands": ["note", "recall", "aggregate", "sync", "resynth", "persona", "view"],
    "widgets": [
        {"id": "chat", "module": "mist_agent.widgets.chat", "class": "ChatPanel", "default": True},
        {"id": "topics", "module": "mist_agent.widgets.topics", "class": "TopicsPanel"},
    ],
}
```

## TUI Structure

The TUI is a thin Textual application:

```
mist-tui/
├── pyproject.toml
└── src/mist_tui/
    ├── __init__.py
    ├── app.py              # MistApp(App): layout shell, widget mounting
    ├── broker_client.py    # BrokerClient: async socket connection
    ├── widget_loader.py    # Dynamic import of agent widgets
    └── keybindings.py      # Global keybinding management
```

The TUI:
1. Connects to the broker
2. Requests the agent catalog
3. For each agent, imports declared widgets and mounts them
4. Manages layout, focus, and keybindings
5. Does not interpret or route agent messages

Each widget receives a `BrokerClient` instance on mount, which it uses to communicate with its agent.

## Data Directory

```
data/
├── shared/
│   ├── mist.db              # Shared tasks, events (SQLite)
│   └── config/
│       └── settings.json    # Global settings
├── agents/
│   ├── mist/
│   │   ├── config/          # persona.md, agent settings
│   │   ├── notes/           # rawLog.jsonl, archive.jsonl
│   │   ├── topics/          # per-topic noteLog.jsonl, synthesis.md
│   │   └── synthesis/       # context.md
│   └── agent-b/
│       ├── config/
│       └── ...
└── broker/
    ├── registry.json        # Known agents, socket paths
    └── mist.sock            # Broker Unix socket
```

## Migration Path

### Phase 1: Extract mist-core
Pull shared infrastructure into its own package: storage, DB, task/event stores, settings, types, protocol definitions. Everything still imports directly — no broker yet.

### Phase 2: Define the protocol
Message envelope, message types, framing. Build transport library (Unix socket async client/server). Test with simple echo agent.

### Phase 3: Build the broker
Agent registry, message routing, shared service wrappers around mist-core, LLM service wrapping Ollama. MIST agent connects to broker, sends/receives messages.

### Phase 4: Separate the TUI
Strip tui.py to layout shell. Build widget loader. Widgets receive BrokerClient. TUI connects to broker, discovers agents, mounts widgets.

### Phase 5: Extract MIST widgets
Move chat and topic panels into mist-agent/widgets/. Widgets communicate through BrokerClient instead of direct imports.

### Phase 6: Remote gateway (future)
Add HTTP/WebSocket listener to broker for phone and multi-device access.

## Note-Taking System (In Progress)

The goal is to make MIST a full note-taking system with LLM-assisted filing, organization, and synthesis. The existing `note` command captures atomic thoughts (Zettelkasten-style); the note-taking system adds long-form markdown documents that supplement those atomic notes.

### Data Model

Each topic gains a `notes/` subdirectory:

```
data/topics/<slug>/
├── noteLog.jsonl       # Classified atomic entries (existing)
├── synthesis.md        # LLM-generated synthesis (existing)
├── about.md            # Topic description (existing)
└── notes/              # Long-form markdown notes (new)
    ├── 2026-02-03-project-plan.md
    ├── 2026-02-04-architecture-thoughts.md
    └── ...
```

Unfiled notes (created without a topic) live in `data/notes/drafts/` until classified.

### Note Creation Paths

1. **Direct create** — Create a new .md file within a topic (or unfiled). User provides a title; filename is `YYYY-MM-DD-<slug-title>.md`.
2. **Promote from noteLog** — Expand a classified noteLog entry into a standalone .md file with LLM assistance at three depth levels:
   - *outline* — bullet structure
   - *draft* — fleshed-out paragraphs
   - *deep* — thorough analysis with `[[wiki-links]]` and short quotes from related notes across topics

### Editing

- **Side-panel editor** — existing TextArea in the TUI viewer panel, for quick edits
- **Full-screen editor** — dedicated view replacing the chat panel, with live markdown preview

### Cross-Linking

Notes support `[[topic/note-name]]` wiki-style links. The LLM discovers and suggests connections during promotion (especially at *deep* level) and synthesis. Links serve as context for synthesis.

### Synthesis Changes

The synthesis pipeline reads all `.md` files from `notes/` alongside `noteLog.jsonl` entries as equal input. Both feed into the same LLM prompts.

### Implementation Order

TUI-first: build the editor widgets and note browsing UI in the TUI package (no agent/broker changes needed). Then add agent-side commands and LLM-assisted promotion.

## Future Considerations

- **Inter-agent communication:** Agents can send messages to each other through the broker. The broker can expose a graph of agent connections.
- **Phone access:** A thin HTTP/WebSocket gateway in front of the broker accepts requests from mobile devices and forwards them as protocol messages.
- **Remote deployment:** Run the broker + agents on a server. TUI and other clients connect over TCP instead of Unix sockets. Protocol is the same.
- **Agentic broker:** The broker itself could gain agent-like capabilities — orchestrating multi-agent workflows, summarizing cross-agent state, etc.
