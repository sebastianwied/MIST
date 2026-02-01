"""Data-access layer for the user profile configuration file."""

from pathlib import Path

USER_PROFILE_PATH = Path("data/config/user.md")
LAST_PROFILE_UPDATE_PATH = Path("data/state/last_profile_update.txt")

DEFAULT_PROFILE = """\
No user profile yet. Run the `profile` command to extract one from conversation history."""


def load_user_profile() -> str:
    """Read the user profile from disk, creating the default file if missing."""
    if not USER_PROFILE_PATH.exists():
        USER_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        USER_PROFILE_PATH.write_text(DEFAULT_PROFILE + "\n", encoding="utf-8")
    return USER_PROFILE_PATH.read_text(encoding="utf-8").strip()


def save_user_profile(text: str) -> None:
    """Write a new user profile to disk."""
    USER_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_PATH.write_text(text.strip() + "\n", encoding="utf-8")


def get_last_profile_update_time() -> str | None:
    """Return the ISO timestamp of the last profile update, or None."""
    try:
        ts = LAST_PROFILE_UPDATE_PATH.read_text(encoding="utf-8").strip()
        return ts or None
    except FileNotFoundError:
        return None


def set_last_profile_update_time(ts: str) -> None:
    """Record the ISO timestamp of the most recently processed entry."""
    LAST_PROFILE_UPDATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_PROFILE_UPDATE_PATH.write_text(ts, encoding="utf-8")
