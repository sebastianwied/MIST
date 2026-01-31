# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MIST is a local-first reflective AI companion system with three interfaces: a macOS desktop app (SwiftUI), a CLI REPL (Python), and a FastAPI backend. All components connect to a local Ollama instance running the `gemma3:1b` model. There are no cloud dependencies.

## Architecture

```
Desktop App (SwiftUI)          CLI (interactor2.py)
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
Ollama (local, gemma3:1b)
```

- **Desktop app** → sends messages via `AgentAPI.callAgent()` to the FastAPI server, which proxies to Ollama
- **CLI interactors** → call Ollama directly via the Python `ollama` library and persist thoughts/notes to `data/`
- **agent/** module → empty placeholder structure for a planned refactored agent package

## Prerequisites

- Python 3.13 with venv at `./env`
- Ollama installed and running (`ollama serve`) with `gemma3:1b` pulled
- Xcode 14.2+ (for desktop app)

## Running the System

```bash
# Activate Python venv
source env/bin/activate

# Start the FastAPI server (required for desktop app)
uvicorn server.app:app --host 127.0.0.1 --port 8765

# Run the CLI interactor
python interactor2.py

# Build desktop app
cd desktop/MistAvatar && xcodebuild -scheme MistAvatar build
```

Python dependencies: `fastapi`, `uvicorn`, `ollama`

## Key Components

| Component | Path | Tech |
|-----------|------|------|
| FastAPI server | `server/app.py` | FastAPI + Pydantic, single `POST /message` endpoint |
| CLI v2 | `interactor2.py` | Python REPL, commands: `status`, `summarize`, `stop`, free-text reflection |
| CLI v1 | `interactor.py` | Python REPL, commands: `note`, `task`, `ask`, `status`, `summarize` |
| Desktop app | `desktop/MistAvatar/MistAvatar/` | SwiftUI macOS app |
| Agent module | `agent/src/mist_agent/` | Empty stubs (planned) |
| Data store | `data/` | Markdown files for logs, notes, journal, tasks |

## Desktop App Structure

The macOS app runs as a menu-bar-style accessory (no dock icon). `AppDelegate` creates two `NSPanel` windows:
- **Avatar panel** (56x56): always-visible floating diamond icon, top-right corner
- **Chat panel** (360x420): toggles on avatar click, positioned left of avatar

`AgentAPI.swift` handles HTTP communication with the FastAPI server. `ChatView.swift` manages the message list and input field via a `ChatModel` ObservableObject.

## Data Flow

- **interactor2.py**: all input logged to `data/notes/rawLog.md` with timestamps; reflections stored in `data/notes/toSynthesize.md`; `summarize` command synthesizes pending notes into `data/agentJournal.md` and caches in `data/state/last_summary.json`
- **server/app.py**: stateless proxy — receives `{text: str}`, returns `{reply: str}` from Ollama

## API

`POST http://127.0.0.1:8765/message`
- Request: `{"text": "user message"}`
- Response: `{"reply": "agent response"}`
