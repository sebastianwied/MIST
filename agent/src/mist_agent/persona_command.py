"""Interactive persona editing command."""

from typing import Callable

from .ollama_client import call_ollama
from .persona import load_persona, save_persona
from .prompts import PERSONA_EDIT_PROMPT
from .types import Writer


def handle_persona(
    output: Writer = print,
    input_fn: Callable[..., str] = input,
) -> None:
    """Run the interactive persona editing loop."""
    working = load_persona()

    output("\n--- Current Persona ---")
    output(working)
    output("-----------------------")
    output("Describe what you'd like to change, or type 'done' to exit.\n")

    try:
        while True:
            try:
                user_input = input_fn("persona> ").strip()
            except EOFError:
                output("")
                return

            if not user_input:
                continue
            if user_input.lower() == "done":
                return

            draft = _generate_draft(working, user_input)
            result = _present_draft(draft, output=output, input_fn=input_fn)

            if result is None:
                # EOFError during prompt
                return
            elif result == "yes":
                save_persona(draft)
                output("Persona updated and saved.\n")
                return
            elif result == "no":
                output("Draft discarded.\n")
                # Stay in loop so user can try again or type 'done'
            else:
                # result is further editing text — refine the draft
                working = draft
                user_input = result
                draft = _generate_draft(working, user_input)
                result = _present_draft(draft, output=output, input_fn=input_fn)

                if result is None:
                    return
                elif result == "yes":
                    save_persona(draft)
                    output("Persona updated and saved.\n")
                    return
                elif result == "no":
                    output("Draft discarded.\n")
                else:
                    working = draft
                    output("Okay, describe further changes.\n")

    except KeyboardInterrupt:
        output("\nPersona editing cancelled.\n")


def _generate_draft(current: str, user_input: str) -> str:
    prompt = PERSONA_EDIT_PROMPT.format(
        current_persona=current,
        user_input=user_input,
    )
    return call_ollama(prompt)


def _present_draft(
    draft: str,
    output: Writer = print,
    input_fn: Callable[..., str] = input,
) -> str | None:
    """Print the draft and ask the user what to do. Returns the choice or None on EOF."""
    output("\n--- Proposed Persona ---")
    output(draft)
    output("------------------------\n")
    try:
        return input_fn("Apply this persona? (yes/no/tell me more changes): ").strip().lower()
    except EOFError:
        output("")
        return None
