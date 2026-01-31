#!/usr/bin/env bash
# Activate the project venv and start the MIST REPL.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
source "$REPO_ROOT/env/bin/activate"
python -m agent.src.mist_agent.main
