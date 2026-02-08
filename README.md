# MIST

A local-first reflective AI companion. A central broker manages agent lifecycle and message routing, while a Textual TUI provides the interface. All components talk to a local [Ollama](https://ollama.com) instance — no cloud dependencies.

## Architecture

```
TUI (mist-tui)          Desktop App (SwiftUI)
  |                        |
  | Unix socket            | HTTP POST 127.0.0.1:8765
  v                        v
Broker (mist-broker)     FastAPI server (legacy)
  |                        |
  v                        v
Agent (mist-agent)       Ollama
  |
  v
Ollama (local)
```

Four packages in one repo:

| Package | Description |
|---------|-------------|
| `mist-core` | Shared infrastructure: storage, settings, types, protocol |
| `mist-broker` | Agent registry, message routing, transport (Unix sockets) |
| `mist-tui` | Textual shell: layout, widget loading, editor screens, keybindings |
| `mist-agent` | MIST agent: persona, topics, notes, synthesis, aggregation, widgets |

## Quick Start

```bash
# Prerequisites: Python 3.13, Ollama running with a model pulled (default: gemma3:1b)

python3 -m venv env
source env/bin/activate

# Install all packages (editable)
pip install -e ./core -e ./broker -e ./agent -e ./tui

# Run in three terminals:
mist-broker          # 1. Start the broker
mist-agent           # 2. Start the agent
mist-tui             # 3. Start the TUI
```

## Data Layout

```
data/
├── mist.db                          # SQLite — tasks, events
├── config/
│   ├── persona.md                   # Agent personality
│   ├── user.md                      # Extracted user profile
│   ├── settings.json                # All settings (model, agency mode, etc.)
│   └── avatar.png                   # Desktop app avatar (optional)
├── notes/
│   ├── rawLog.jsonl                 # JSONL log of all user input
│   ├── archive.jsonl                # Entries archived during aggregation
│   └── drafts/                      # Unfiled long-form notes
│       └── YYYY-MM-DD-<title>.md
├── topics/
│   ├── index.json                   # Topic metadata
│   └── <slug>/
│       ├── noteLog.jsonl            # Topic-specific classified entries
│       ├── synthesis.md             # LLM-generated topic synthesis
│       ├── about.md                 # Topic description (optional)
│       └── notes/                   # Long-form notes filed to this topic
│           └── YYYY-MM-DD-<title>.md
├── synthesis/
│   └── context.md                   # Condensed cross-topic context
└── state/
    ├── last_aggregate.txt           # Timestamp bookmark
    └── last_sync.txt                # Timestamp bookmark
```

## Commands

### Notes & Reflection

| Command | Description |
|---------|-------------|
| `note <text>` | Save a note silently (no LLM call) |
| `note new [topic] <title>` | Create a long-form note (in topic or as draft) |
| `note list <topic\|drafts>` | List note files in a topic or drafts |
| `note file <filename> <topic>` | File a draft note into a topic |
| `note promote <topic> <index> [depth]` | Expand a noteLog entry into a note via LLM |
| `notes` | List recent notes |
| `recall <topic>` | Search all past input via LLM |
| `aggregate` | Classify new log entries into topics via LLM |
| `topic add <name>` | Manually create a topic |
| `topic about <id\|slug> [text]` | View or set a topic description |
| `topic merge <source> <target>` | Merge source topic into target (entries, notes, synthesis) |
| `reset topics` | Undo aggregation — move topic entries back to rawLog |
| `sync` | Update per-topic synthesis with new entries |
| `resynth` | Full rewrite of all synthesis (deep model) |
| `synthesis <id\|slug>` | Resynthesize a single topic |

### Tasks

| Command | Description |
|---------|-------------|
| `task add <title> [due:YYYY-MM-DD]` | Create a task |
| `task list [all]` / `tasks` | List tasks |
| `task done <id>` | Mark done |
| `task delete <id>` | Delete |

### Events

| Command | Description |
|---------|-------------|
| `event add <title> <date> <time>[-end] [freq] [until:date]` | Create event |
| `event list [days]` / `events` | List upcoming |
| `event delete <id>` | Delete |

### Viewing & Editing

| Command | Description |
|---------|-------------|
| `view <name>` | View a file or data (read-only): `persona`, `user`, `context`, `rawlog`, `synthesis`, `topics`, `tasks`, `events`, `model` |
| `edit <name>` | Edit a file: `persona`, `user`, `rawlog`, `context` |
| F3 | Toggle between full-screen and side-panel editor |

### Settings & System

| Command | Description |
|---------|-------------|
| `settings` | Show all settings |
| `set <key> <value>` | Change a setting |
| `set model <name>` | Set default Ollama model |
| `persona` | Interactively edit personality via LLM |
| `status` | System status |
| `stop` | Unload model |
| `help` | Show commands |

Settings: `agency_mode` (suggest/auto/off), `context_tasks_days`, `context_events_days`, `model`, `model_<cmd>`.

## Configuration

Config files in `data/config/` are gitignored and auto-created from defaults on first run.

| File | Purpose |
|------|---------|
| `persona.md` | Agent personality |
| `settings.json` | All settings including model selection |
| `avatar.png` | Desktop app avatar (optional) |

## Dependencies

Python: `ollama`, `textual`, `fastapi`, `uvicorn`
