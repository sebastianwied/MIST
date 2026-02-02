# MIST

A local-first reflective AI companion with a macOS desktop app, a CLI REPL, a TUI, and a FastAPI backend. All components talk to a local [Ollama](https://ollama.com) instance — no cloud dependencies.

## Quick Start

```bash
# Prerequisites: Python 3.13, Ollama running with a model pulled (default: gemma3:1b)

# Create and activate a Python venv
python3 -m venv env
source env/bin/activate

# Install the agent package (editable) and the server package
pip install -e ./agent
pip install -e ./server

# Run the TUI (recommended)
mist

# Or run the plain REPL
mist-repl

# Start the FastAPI server (required for the desktop app)
uvicorn server.app:app --host 127.0.0.1 --port 8765
```

Build the macOS desktop app in Xcode: open `desktop/MistAvatar/MistAvatar.xcodeproj` and run.

## Data Layout

```
data/
├── mist.db                          # SQLite — tasks, events, recurrence rules
├── agentJournal.md                  # Summarized journal entries
├── config/
│   ├── persona.md                   # Agent personality
│   ├── user.md                      # Extracted user profile
│   ├── model.conf                   # Ollama model name (default: gemma3:1b)
│   ├── deep_model.conf              # Model for resynth (fallback: model.conf)
│   ├── settings.json                # Agency mode, context windows
│   └── avatar.png                   # Desktop app avatar (optional)
├── notes/
│   ├── rawLog.jsonl                 # JSONL log of all user input
│   └── archive.jsonl                # Entries moved out during aggregation
├── topics/
│   ├── index.json                   # Topic metadata
│   └── <slug>/                      # Per-topic directory
│       ├── noteLog.jsonl            # Topic-specific entries
│       ├── synthesis.md             # Topic synthesis
│       └── about.md                 # Topic description (optional)
├── synthesis/
│   └── context.md                   # Condensed context injected into prompts
└── state/
    ├── last_aggregate.txt           # Timestamp bookmark for aggregate
    └── last_sync.txt                # Timestamp bookmark for sync
```

## REPL Commands

### Notes & Reflection

| Command | Description |
|---------|-------------|
| `note <text>` | Save a note silently (no LLM call) |
| `notes` | List recent notes |
| `recall <topic>` | Search all past input via LLM |
| `aggregate` | Classify new log entries into topics via LLM |
| `topic add <name>` | Manually create a topic |
| `topic about <id\|slug> [text]` | View or set a topic description |
| `reset topics` | Undo aggregation — move topic entries back to rawLog |
| `sync` | Update per-topic synthesis files with new entries |
| `resynth` | Full rewrite of all synthesis files using the deep model |
| `synthesis <id\|slug>` | Resynthesize a single topic |
| Free text | Reflected back by the agent (may detect tasks/events depending on agency setting) |

### Tasks

| Command | Description |
|---------|-------------|
| `task add <title> [due:YYYY-MM-DD]` | Create a task with optional due date |
| `task list [all]` or `tasks` | List open tasks (add `all` to include done/cancelled) |
| `task done <id>` | Mark a task as done |
| `task delete <id>` | Delete a task |

### Events

| Command | Description |
|---------|-------------|
| `event add <title> <YYYY-MM-DD> <HH:MM>[-HH:MM] [frequency] [until:YYYY-MM-DD]` | Create an event (optionally recurring) |
| `event list [days]` or `events` | List upcoming events (default 7 days) |
| `event delete <id>` | Delete an event |

Recurrence frequencies: `daily`, `weekly`, `monthly`, `yearly`.

### Settings & System

| Command | Description |
|---------|-------------|
| `settings` | Show all current settings |
| `set <key> <value>` | Change a setting |
| `persona` | Interactively edit the agent's personality via LLM |
| `view <name>` | Display a file or data view (`persona`, `user`, `tasks`, `events`, `synthesis`, etc.) |
| `status` | Show system status |
| `stop` | Unload the model |
| `help` | Show available commands |

Available settings:

| Key | Values | Default | Description |
|-----|--------|---------|-------------|
| `agency_mode` | `suggest`, `auto`, `off` | `suggest` | How the agent handles detected tasks/events in free text |
| `context_tasks_days` | integer | `7` | Days of upcoming tasks injected into agent context |
| `context_events_days` | integer | `3` | Days of upcoming events injected into agent context |
| `model` | model name | `gemma3:1b` | Default Ollama model for all commands |
| `model_<cmd>` | model name | (inherits `model`) | Per-command model override (e.g. `model_resynth`) |

Available per-command model keys: `model_reflect`, `model_recall`, `model_sync`, `model_resynth`, `model_synthesis`, `model_aggregate`, `model_extract`, `model_persona`, `model_profile`.

## Configuration

Config files are auto-created from defaults on first run and are gitignored so `git pull` never overwrites them.

All configuration lives in `data/config/`:

| File | Purpose |
|------|---------|
| `persona.md` | Agent personality — edit directly or via the `persona` REPL command |
| `model.conf` | Legacy model name file (use `set model <name>` instead; migrated to settings.json on startup) |
| `deep_model.conf` | Legacy deep model file (migrated to `model_resynth`/`model_synthesis` on startup) |
| `settings.json` | All settings including model selection — managed via `set` command |
| `avatar.png` | Desktop app avatar image (optional, falls back to diamond icon) |

## Entry Points

| Command | Source | Description |
|---------|--------|-------------|
| `mist` | `agent/pyproject.toml` | Textual TUI (recommended) |
| `mist-repl` | `agent/pyproject.toml` | Plain terminal REPL |
| `uvicorn server.app:app` | `server/` | FastAPI server for the desktop app |

## API

`POST http://127.0.0.1:8765/message`
- Request: `{"text": "user message"}`
- Response: `{"reply": "agent response"}`

## Dependencies

Python: `ollama`, `textual`, `fastapi`, `uvicorn`
