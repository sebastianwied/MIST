"""Handler for the 'profile' command."""

from mist_core.ollama_client import call_ollama
from mist_core.storage import RawLogEntry, parse_rawlog
from mist_core.types import Writer

from .notes import _format_entries
from .profile import (
    get_last_profile_update_time,
    load_user_profile,
    save_user_profile,
    set_last_profile_update_time,
)
from .prompts import PROFILE_EXTRACTION_PROMPT


def handle_profile(output: Writer = print, entries: list[RawLogEntry] | None = None) -> None:
    """Extract user facts from entries and update user.md.

    If *entries* is None, reads from rawLog and filters by high-water mark.
    """
    if entries is None:
        entries = parse_rawlog()
        high_water = get_last_profile_update_time()
        if high_water:
            entries = [e for e in entries if e.time > high_water]
    else:
        high_water = None

    current_profile = load_user_profile()

    if not entries:
        output("No new entries to process.\n")
        output("Current profile:\n")
        output(current_profile)
        return

    output(f"Extracting profile from {len(entries)} entries...")
    formatted = _format_entries(entries)
    prompt = PROFILE_EXTRACTION_PROMPT.format(
        current_profile=current_profile,
        entries=formatted,
    )
    updated = call_ollama(prompt, command="profile")

    save_user_profile(updated)
    set_last_profile_update_time(entries[-1].time)
    output("Profile updated → data/config/user.md")
