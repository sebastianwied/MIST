from pathlib import Path
import shlex
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class Command:
    name: str
    args: List[str]

noteFolderPath = Path("test.md")
toSynthPath = Path("toSynthesize.md")
agentJournalPath = Path("agentJournal.md")
rawLogPath = Path("rawLog.md")

class CommandParseError(Exception):
    pass

def parse_command(line: str) -> Command:
    """
    Parse a single command line into a Command object.

    Examples:
        note "some text"
        task add "email advisor"
        ask "what have I written about X?"
        status
    """
    try:
        tokens = shlex.split(line)
    except ValueError as e:
        raise CommandParseError(f"Invalid quoting: {e}")

    if not tokens:
        raise CommandParseError("Empty command")

    name = tokens[0]
    args = tokens[1:]

    return Command(name=name, args=args)

def dispatch(cmd: Command):
    if cmd.name == "note":
        if not cmd.args:
            raise CommandParseError("note requires text")
        if len(cmd.args) == 1:
            text = " ".join(cmd.args)
            handle_note(text)
        elif cmd.args[0] == "from":
            handle_note_file(" ".join(cmd.args[1:]))

    elif cmd.name == "task":
        if len(cmd.args) < 2:
            raise CommandParseError("task requires a subcommand and text")
        subcmd = cmd.args[0]
        text = " ".join(cmd.args[1:])
        handle_task(subcmd, text)

    elif cmd.name == "ask":
        if not cmd.args:
            raise CommandParseError("ask requires a query")
        query = " ".join(cmd.args)
        handle_ask(query)

    elif cmd.name == "status":
        handle_status()
    
    elif cmd.name == "summarize":
        handle_summarization()

    else:
        raise CommandParseError(f"Unknown command: {cmd.name}")

def handle_note_file(file, source="import"):
    with open(Path(file),"r") as f:
        text = f.read()
    handle_note(text, source)

def handle_note(text, source: str = "terminal"):
    path = toSynthPath
    path.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat(timespec="seconds")

    entry = f"""---
time: {timestamp}
source: {source}
---

{text.strip()}
"""

    with path.open("a", encoding="utf-8") as f:
        f.write(entry)

def handle_task(subcmd, text):
    print(f"Handling task {subcmd} with text {text}")
    pass

def handle_ask(query):
    print(f"Handling question: {query}")
    pass

def handle_status():
    pass

import subprocess

from ollama import chat
from ollama import ChatResponse

def call_ollama(
    prompt: str,
    model: str = "gemma3:1b",
    temperature: float = 0.3,
) -> str:
    """
    Calls Ollama and returns the raw text output.
    """
    response: ChatResponse = chat(model=model, messages=[
        {
            'role': 'user',
            'content': prompt,
        },
    ])

    return response['message']['content']

def handle_summarization():
    toSummarize = toSynthPath.read_text(encoding="utf-8")
    with open(rawLogPath, "a") as f:
        f.write("\n")
        f.write(toSummarize)
    prompt = f"""You are a reflective assistant maintaining a personal thinking log.

Task:
Summarize the user's recent thoughts.

Guidelines:
- Do not invent information
- Do not give advice or recommendations
- Identify recurring themes, questions, and unresolved ideas
- Note contradictions or shifts in thinking if present
- Be concise and structured

Recent notes:
{toSummarize}

Summary:
"""
    summary = call_ollama(prompt)
    with open(agentJournalPath, 'a') as f:
        f.write(summary)
        f.write("\n")
    with open(toSynthPath, "w") as f:
        pass

def repl():
    while True:
        try:
            line = input("> ").strip()
            if line in {"exit", "quit"}:
                break

            cmd = parse_command(line)
            dispatch(cmd)

        except CommandParseError as e:
            print(f"Error: {e}")
        except KeyboardInterrupt:
            print("\nExiting.")
            break

repl()