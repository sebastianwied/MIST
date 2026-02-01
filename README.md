# MIST

A local-first reflective AI companion with a macOS desktop app, a CLI REPL, and a FastAPI backend. All components talk to a local [Ollama](https://ollama.com) instance — no cloud dependencies.

## Quick Start

```bash
# Prerequisites: Python 3.13, Ollama with a model pulled (default: gemma3:1b)

# Activate the Python venv
source env/bin/activate

# Start the FastAPI server (required for the desktop app)
uvicorn server.app:app --host 127.0.0.1 --port 8765

# Run the CLI
python -m mist_agent.main
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
│   ├── model.conf                   # Ollama model name
│   ├── deep_model.conf              # Model for resynth (fallback: model.conf)
│   ├── settings.json                # Agency mode, context windows
│   └── avatar.png                   # Desktop app avatar (optional)
├── notes/
│   ├── rawLog.md                    # Timestamped log of all user input
│   └── rawLog_archive.md            # Rotated older entries
├── synthesis/
│   ├── context.md                   # Condensed context injected into prompts
│   └── *.md                         # Per-topic synthesis files
└── state/
    ├── last_summarized.txt          # Timestamp bookmark for summarize
    └── last_sync.txt                # Timestamp bookmark for sync
```

## REPL Commands

### Notes & Reflection

| Command | Description |
|---------|-------------|
| `note <text>` | Save a note silently (no LLM call) |
| `notes` | List recent notes |
| `recall <topic>` | Search all past input via LLM |
| `sync` | Update the master synthesis file with new themes |
| `resynth` | Full rewrite of the synthesis file using the deep model |
| `summarize` | Summarize new log entries into the journal |
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
| `stop` | Stop the model |

Available settings:

| Key | Values | Default | Description |
|-----|--------|---------|-------------|
| `agency_mode` | `suggest`, `auto`, `off` | `suggest` | How the agent handles detected tasks/events in free text |
| `context_tasks_days` | integer | `7` | Days of upcoming tasks injected into agent context |
| `context_events_days` | integer | `3` | Days of upcoming events injected into agent context |

## Configuration

All configuration lives in `data/config/`:

| File | Purpose |
|------|---------|
| `persona.md` | Agent personality — edit directly or via the `persona` REPL command |
| `model.conf` | Ollama model name (one line, e.g. `gemma3:12b`) |
| `deep_model.conf` | Model used by `resynth` (falls back to `model.conf`) |
| `settings.json` | Agent settings (agency mode, context windows) — managed via `set` command |
| `avatar.png` | Desktop app avatar image (optional, falls back to diamond icon) |

Data is stored in `data/`:

| Path | Purpose |
|------|---------|
| `data/mist.db` | SQLite database for tasks and events |
| `data/notes/rawLog.md` | Timestamped log of all user input |
| `data/agentJournal.md` | Summarized journal entries |
| `data/synthesis/` | Topic synthesis files and context summary |

## API

`POST http://127.0.0.1:8765/message`
- Request: `{"text": "user message"}`
- Response: `{"reply": "agent response"}`

## Dependencies

Python: `fastapi`, `uvicorn`, `ollama`
