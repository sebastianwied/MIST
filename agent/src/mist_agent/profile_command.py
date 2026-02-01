"""Handler for the 'profile' command."""

from .notes import _format_entries
from .ollama_client import call_ollama
from .profile import (
    get_last_profile_update_time,
    load_user_profile,
    save_user_profile,
    set_last_profile_update_time,
)
from .prompts import PROFILE_EXTRACTION_PROMPT
from .storage import parse_rawlog


def handle_profile() -> None:
    """Extract user facts from new rawLog entries and update user.md."""
    entries = parse_rawlog()
    high_water = get_last_profile_update_time()

    if high_water:
        entries = [e for e in entries if e.time > high_water]

    current_profile = load_user_profile()

    if not entries:
        print("No new entries to process.\n")
        print("Current profile:\n")
        print(current_profile)
        return

    print(f"Extracting profile from {len(entries)} entries...")
    formatted = _format_entries(entries)
    prompt = PROFILE_EXTRACTION_PROMPT.format(
        current_profile=current_profile,
        entries=formatted,
    )
    updated = call_ollama(prompt)

    save_user_profile(updated)
    set_last_profile_update_time(entries[-1].time)
    print("Profile updated → data/config/user.md")
