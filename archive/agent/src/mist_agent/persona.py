"""Data-access layer for the persona configuration file."""

from pathlib import Path

PERSONA_PATH = Path("data/config/persona.md")

DEFAULT_PERSONA = """\
You are a utilitarian, reflective assistant embedded in a personal living notepad.

Your role is NOT to make decisions, set goals, or think on behalf of the user.
Your role IS to:
- acknowledge what the user just expressed
- help clarify or lightly reframe thoughts
- surface possible interpretations without committing to any of them
- support recall and reflection over time"""


def load_persona() -> str:
    """Read the persona from disk, creating the default file if missing."""
    if not PERSONA_PATH.exists():
        PERSONA_PATH.parent.mkdir(parents=True, exist_ok=True)
        PERSONA_PATH.write_text(DEFAULT_PERSONA + "\n", encoding="utf-8")
    return PERSONA_PATH.read_text(encoding="utf-8").strip()


def save_persona(text: str) -> None:
    """Write a new persona to disk."""
    PERSONA_PATH.parent.mkdir(parents=True, exist_ok=True)
    PERSONA_PATH.write_text(text.strip() + "\n", encoding="utf-8")
