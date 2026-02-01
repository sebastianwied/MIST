"""Handler for free-text reflection input."""

from .ollama_client import call_ollama
from .persona import load_persona
from .profile import load_user_profile
from .prompts import SYSTEM_PROMPT, USER_PROMPT
from .storage import save_raw_input


def handle_text(text: str, source: str = "terminal") -> str:
    """Log the input and return a reflective response from Ollama."""
    save_raw_input(text, source=source)
    persona = load_persona()
    user_profile = load_user_profile()
    system = SYSTEM_PROMPT.format(persona=persona, user_profile=user_profile)
    prompt = USER_PROMPT.format(text=text)
    return call_ollama(prompt, system=system)
