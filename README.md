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

## REPL Commands

| Command | Description |
|---------|-------------|
| `status` | Show system status |
| `summarize` | Synthesize pending notes into the journal |
| `persona` | Interactively edit the agent's personality via LLM |
| `stop` | Stop the model |
| Free text | Reflected back by the agent |

## Configuration

All configuration lives in `data/config/`:

| File | Purpose |
|------|---------|
| `persona.md` | Agent personality — edit directly or via the `persona` REPL command |
| `model.conf` | Ollama model name (one line, e.g. `gemma3:12b`) |
| `avatar.png` | Desktop app avatar image (optional, falls back to diamond icon) |

## API

`POST http://127.0.0.1:8765/message`
- Request: `{"text": "user message"}`
- Response: `{"reply": "agent response"}`

## Dependencies

Python: `fastapi`, `uvicorn`, `ollama`
