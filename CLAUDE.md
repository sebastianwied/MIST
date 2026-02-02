# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MIST is a local-first reflective AI companion system with three interfaces: a macOS desktop app (SwiftUI), a Textual TUI, and a plain CLI REPL (Python). All connect to a local Ollama instance — no cloud dependencies.

## Architecture

```
Desktop App (SwiftUI)       TUI (Textual)         CLI REPL
       │                        │                     │
  HTTP POST              Direct ollama lib      Direct ollama lib
  127.0.0.1:8765                │                     │
       │                        └──── mist_agent ─────┘
       ▼                              │
FastAPI Server (server/app.py)        ├── data/notes/rawLog.jsonl
       │                              ├── data/topics/<slug>/noteLog.jsonl
  ollama.chat()                       ├── data/mist.db (SQLite)
       │                              └── data/synthesis/context.md
       ▼
Ollama (local)
```

- **Desktop app** → sends messages via `AgentAPI.callAgent()` to the FastAPI server, which proxies to Ollama
- **TUI** → `mist` — Textual-based interface with panels for chat, topics, tasks, and events
- **CLI REPL** → `mist-repl` — plain terminal loop, same command set as TUI
- **agent/** module → the main Python package (`mist_agent`) containing all agent logic

## Prerequisites

- Python 3.13 with venv
- Ollama installed and running (`ollama serve`) with a model pulled (default `gemma3:1b`)
- Xcode 14.2+ (for desktop app only)

## Running the System

```bash
# Create and activate Python venv
python3 -m venv env
source env/bin/activate

# Install packages (editable)
pip install -e ./agent
pip install -e ./server

# Run the TUI (recommended)
mist

# Or run the plain REPL
mist-repl

# Start the FastAPI server (required for desktop app)
uvicorn server.app:app --host 127.0.0.1 --port 8765

# Build desktop app
cd desktop/MistAvatar && xcodebuild -scheme MistAvatar build
```

Python dependencies: `ollama`, `textual`, `fastapi`, `uvicorn`

## Key Components

| Component | Path | Tech |
|-----------|------|------|
| FastAPI server | `server/app.py` | FastAPI + Pydantic, single `POST /message` endpoint |
| TUI | `agent/src/mist_agent/tui.py` | Textual app with chat, topic, task, and event panels |
| CLI REPL | `agent/src/mist_agent/main.py` | Plain terminal REPL with spinner support |
| Commands | `agent/src/mist_agent/commands.py` | Central command dispatcher |
| Aggregation | `agent/src/mist_agent/aggregate.py` | LLM-based topic classification and routing |
| Synthesis | `agent/src/mist_agent/synthesis.py` | Per-topic and global synthesis generation |
| Storage | `agent/src/mist_agent/storage.py` | JSONL persistence, topic index, file paths |
| Task store | `agent/src/mist_agent/task_store.py` | SQLite-backed task CRUD |
| Event store | `agent/src/mist_agent/event_store.py` | SQLite-backed event CRUD with recurrence |
| Database | `agent/src/mist_agent/db.py` | SQLite connection and schema |
| Ollama client | `agent/src/mist_agent/ollama_client.py` | Ollama API wrapper (standard + deep model) |
| Prompts | `agent/src/mist_agent/prompts.py` | All LLM prompt templates |
| Desktop app | `desktop/MistAvatar/MistAvatar/` | SwiftUI macOS app |
| Data store | `data/` | JSONL logs, SQLite database, markdown synthesis files |
| Config | `data/config/` | `persona.md`, `model.conf`, `deep_model.conf`, `avatar.png` |

## Desktop App Structure

The macOS app runs as a menu-bar-style accessory (no dock icon). `AppDelegate` creates two `NSPanel` windows:
- **Avatar panel** (56x56): always-visible floating avatar, top-right corner. Displays `data/config/avatar.png` if present, otherwise a diamond icon.
- **Chat panel** (360x420): toggles on avatar click, positioned left of avatar

`AgentAPI.swift` handles HTTP communication with the FastAPI server. `ChatView.swift` manages the message list and input field via a `ChatModel` ObservableObject.

## Configuration

All user-editable config is in `data/config/`:
- `persona.md` — agent personality (editable via `persona` REPL command or by hand)
- `model.conf` — Ollama model name, one line (e.g. `gemma3:1b`)
- `deep_model.conf` — model for synthesis commands (falls back to `model.conf`)
- `avatar.png` — optional custom avatar image for the desktop app

The model and persona are read from disk on every call, so edits take effect immediately.

## Data Flow

- **Input logging**: all input logged to `data/notes/rawLog.jsonl` as JSONL (`{time, source, text}`)
- **Aggregation**: `aggregate` command classifies rawLog entries into topics via LLM, routes them to `data/topics/<slug>/noteLog.jsonl`, and archives handled entries to `data/notes/archive.jsonl`
- **Synthesis**: `sync` generates per-topic synthesis from new entries; `resynth` does a full rewrite using the deep model. Global context written to `data/synthesis/context.md`
- **Tasks/Events**: stored in `data/mist.db` (SQLite). Free-text input can auto-detect tasks/events when `agency_mode` is `suggest` or `auto`
- **server/app.py**: stateless proxy — receives `{text: str}`, returns `{reply: str}` from Ollama. Uses the same `handle_text()` path as the REPL, so persona and model config apply.

## API

`POST http://127.0.0.1:8765/message`
- Request: `{"text": "user message"}`
- Response: `{"reply": "agent response"}`
