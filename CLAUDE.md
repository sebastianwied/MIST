# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MIST is a local-first reflective AI companion system with two interfaces: a macOS desktop app (SwiftUI) and a CLI REPL (Python). Both connect to a local Ollama instance via a FastAPI backend. There are no cloud dependencies.

## Architecture

```
Desktop App (SwiftUI)          CLI REPL (mist_agent)
       │                              │
  HTTP POST                    Direct ollama lib
  127.0.0.1:8765                      │
       │                              ├── data/notes/rawLog.md
       ▼                              ├── data/notes/toSynthesize.md
FastAPI Server (server/app.py)        └── data/agentJournal.md
       │
  ollama.chat()
       │
       ▼
Ollama (local)
```

- **Desktop app** → sends messages via `AgentAPI.callAgent()` to the FastAPI server, which proxies to Ollama
- **CLI REPL** → `python -m mist_agent.main` — calls Ollama directly via the Python `ollama` library and persists thoughts/notes to `data/`
- **agent/** module → the main Python package (`mist_agent`) containing all agent logic

## Prerequisites

- Python 3.13 with venv at `./env`
- Ollama installed and running (`ollama serve`) with a model pulled (default `gemma3:1b`)
- Xcode 14.2+ (for desktop app)

## Running the System

```bash
# Activate Python venv
source env/bin/activate

# Start the FastAPI server (required for desktop app)
uvicorn server.app:app --host 127.0.0.1 --port 8765

# Run the CLI REPL
python -m mist_agent.main

# Build desktop app
cd desktop/MistAvatar && xcodebuild -scheme MistAvatar build
```

Python dependencies: `fastapi`, `uvicorn`, `ollama`

## Key Components

| Component | Path | Tech |
|-----------|------|------|
| FastAPI server | `server/app.py` | FastAPI + Pydantic, single `POST /message` endpoint |
| CLI REPL | `agent/src/mist_agent/main.py` | Python REPL, commands: `status`, `summarize`, `persona`, `stop`, free-text reflection |
| Desktop app | `desktop/MistAvatar/MistAvatar/` | SwiftUI macOS app |
| Agent module | `agent/src/mist_agent/` | Core agent logic: ollama client, persona, prompts, commands |
| Data store | `data/` | Markdown files for logs, notes, journal |
| Config | `data/config/` | `persona.md`, `model.conf`, `avatar.png` |

## Desktop App Structure

The macOS app runs as a menu-bar-style accessory (no dock icon). `AppDelegate` creates two `NSPanel` windows:
- **Avatar panel** (56x56): always-visible floating avatar, top-right corner. Displays `data/config/avatar.png` if present, otherwise a diamond icon.
- **Chat panel** (360x420): toggles on avatar click, positioned left of avatar

`AgentAPI.swift` handles HTTP communication with the FastAPI server. `ChatView.swift` manages the message list and input field via a `ChatModel` ObservableObject.

## Configuration

All user-editable config is in `data/config/`:
- `persona.md` — agent personality (editable via `persona` REPL command or by hand)
- `model.conf` — Ollama model name, one line (e.g. `gemma3:12b`)
- `avatar.png` — optional custom avatar image for the desktop app

The model and persona are read from disk on every call, so edits take effect immediately.

## Data Flow

- **REPL**: all input logged to `data/notes/rawLog.md` with timestamps; `summarize` command synthesizes pending notes into `data/agentJournal.md`
- **server/app.py**: stateless proxy — receives `{text: str}`, returns `{reply: str}` from Ollama. Uses the same `handle_text()` path as the REPL, so persona and model config apply.

## API

`POST http://127.0.0.1:8765/message`
- Request: `{"text": "user message"}`
- Response: `{"reply": "agent response"}`
