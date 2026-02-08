# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MIST is a modular AI assistant. A single Python core process runs services, a message broker, and the admin agent. External agents connect via Unix sockets using the `mist-client` library. A Tauri UI connects via WebSocket.

See `ARCHITECTURE.md` for the full design.

## Repository Layout

```
mist/
├── archive/          # v1 code (reference only — do not modify)
├── core/             # mist-core: services, broker, admin agent, transport
│   ├── pyproject.toml
│   ├── src/mist_core/
│   └── tests/
├── client/           # mist-client: standalone agent SDK
│   ├── pyproject.toml
│   ├── src/mist_client/
│   └── tests/
├── agents/
│   ├── notes/        # Notes agent (depends on mist-client only)
│   └── science/      # Science agent (depends on mist-client only)
├── ui/               # Tauri app (Phase 7)
└── data/             # Runtime data (gitignored)
```

## Build & Test

Each package is independently installable:

```bash
# Install a package in editable mode
cd core && pip install -e .
cd client && pip install -e .
cd agents/notes && pip install -e .

# Run tests for a single package
cd core && pytest tests/ -v
cd client && pytest tests/ -v
```

**Run only the relevant test suite**, not all packages, unless verifying a cross-cutting change.

## Token Usage

- **Never read files in `data/`** — runtime data, not source code.
- **Never modify files in `archive/`** — reference only. Read when porting.
- Prefer targeted `Grep`/`Glob` over broad exploration.
- Avoid re-reading files already in context.

## Key Patterns

- **Dependency injection via `Paths`**: All classes accept a `Paths(root)` instance. Tests use `Paths(tmp_path)` for isolation — no monkeypatching.
- **Agents never import core**: External agents depend only on `mist-client`. The protocol file is vendored (copied, not imported).
- **Structured responses**: All agent responses use typed JSON (`text`, `table`, `list`, `editor`, `confirm`, `progress`, `error`).
- **Namespaced storage**: The broker injects `agent_id` into service requests. Each agent's files live under `data/agents/<agent_id>/`.

## Conventions

- Use `dataclass(frozen=True)` for protocol messages and value objects.
- Use `async/await` for transport and LLM calls.
- Storage classes are synchronous (SQLite, filesystem).
- Tests use `pytest` with `tmp_path` fixtures for isolation.
