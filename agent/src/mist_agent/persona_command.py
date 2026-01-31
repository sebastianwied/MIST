"""Interactive persona editing command."""

from .ollama_client import call_ollama
from .persona import load_persona, save_persona
from .prompts import PERSONA_EDIT_PROMPT


def handle_persona() -> None:
    """Run the interactive persona editing loop."""
    working = load_persona()

    print("\n--- Current Persona ---")
    print(working)
    print("-----------------------")
    print("Describe what you'd like to change, or type 'done' to exit.\n")

    try:
        while True:
            try:
                user_input = input("persona> ").strip()
            except EOFError:
                print()
                return

            if not user_input:
                continue
            if user_input.lower() == "done":
                return

            draft = _generate_draft(working, user_input)
            result = _present_draft(draft)

            if result is None:
                # EOFError during prompt
                return
            elif result == "yes":
                save_persona(draft)
                print("Persona updated and saved.\n")
                return
            elif result == "no":
                print("Draft discarded.\n")
                # Stay in loop so user can try again or type 'done'
            else:
                # result is further editing text — refine the draft
                working = draft
                user_input = result
                draft = _generate_draft(working, user_input)
                result = _present_draft(draft)

                if result is None:
                    return
                elif result == "yes":
                    save_persona(draft)
                    print("Persona updated and saved.\n")
                    return
                elif result == "no":
                    print("Draft discarded.\n")
                else:
                    working = draft
                    print("Okay, describe further changes.\n")

    except KeyboardInterrupt:
        print("\nPersona editing cancelled.\n")


def _generate_draft(current: str, user_input: str) -> str:
    prompt = PERSONA_EDIT_PROMPT.format(
        current_persona=current,
        user_input=user_input,
    )
    return call_ollama(prompt)


def _present_draft(draft: str) -> str | None:
    """Print the draft and ask the user what to do. Returns the choice or None on EOF."""
    print("\n--- Proposed Persona ---")
    print(draft)
    print("------------------------\n")
    try:
        return input("Apply this persona? (yes/no/tell me more changes): ").strip().lower()
    except EOFError:
        print()
        return None
