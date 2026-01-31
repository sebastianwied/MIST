"""Handlers for sync and resynth commands."""

from .notes import _format_entries
from .ollama_client import call_ollama, load_deep_model
from .prompts import RESYNTH_PROMPT, SYNC_PROMPT
from .storage import SYNTHESIS_PATH, parse_rawlog


def handle_sync() -> None:
    """Incrementally update the master synthesis file."""
    print("Syncing synthesis...")
    entries = parse_rawlog()
    if not entries:
        print("No entries to synthesize.")
        return

    try:
        current = SYNTHESIS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""

    formatted = _format_entries(entries)
    prompt = SYNC_PROMPT.format(
        current_synthesis=current or "(empty — first synthesis)",
        new_entries=formatted,
    )
    result = call_ollama(prompt)

    SYNTHESIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNTHESIS_PATH.write_text(result, encoding="utf-8")
    print("Synthesis updated (data/notes/synthesis.md).")


def handle_resynth() -> None:
    """Full rewrite of the synthesis file using the deep model."""
    deep_model = load_deep_model()
    print(f"Deep resynthesis using {deep_model}...")

    entries = parse_rawlog()
    if not entries:
        print("No entries to synthesize.")
        return

    formatted = _format_entries(entries)
    prompt = RESYNTH_PROMPT.format(all_entries=formatted)
    result = call_ollama(prompt, model=deep_model)

    SYNTHESIS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNTHESIS_PATH.write_text(result, encoding="utf-8")
    print("Synthesis rewritten (data/notes/synthesis.md).")
