from pathlib import Path
import shlex
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
import subprocess
from ollama import chat
from ollama import ChatResponse

@dataclass
class Command:
    name: str
    args: List[str]
    all: str

noteFolderPath = Path("test.md")
toSynthPath = Path("toSynthesize.md")
agentJournalPath = Path("agentJournal.md")
rawLogPath = Path("rawLog.md")

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
    all = " ".join(tokens)

    return Command(name=name, args=args, all=all)

def dispatch(cmd: Command):
    if cmd.name == "status" and len(cmd.args) == 0:
        handle_status()
    
    elif cmd.name == "summarize" and len(cmd.args) == 0:
        handle_summarization()
    
    elif cmd.name == "stop" and len(cmd.args) == 0:
        subprocess.run(["ollama", "stop", "gemma3:1b"])
    
    elif cmd.name == "debug" and len(cmd.args) == 0:
        pass

    else:
        handle_text(cmd.all)

def handle_status():
    print("status check...")
    pass

def saveRawInput(text, source="terminal"):
    timestamp = datetime.now().isoformat(timespec="seconds")
    entry = f"""---
time: {timestamp}
source: {source}
---

{text.strip()}
"""
    with open(rawLogPath, "a") as f:
        f.write("\n")
        f.write(entry)

def handle_text(text):
    # Store input
    saveRawInput(text, source="raw input")
    prompt = f"""You are a utilitarian, reflective assistant embedded in a personal living notepad.

Your role is NOT to make decisions, set goals, or think on behalf of the user.
Your role IS to:
- acknowledge what the user just expressed
- help clarify or lightly reframe thoughts
- surface possible interpretations without committing to any of them
- support recall and reflection over time

You must follow these constraints strictly:

1. Do not give advice, recommendations, or instructions unless explicitly asked.
2. Do not create or assign tasks on your own.
3. Do not assume intent beyond what is stated.
4. Do not invent context, plans, or motivations.
5. Do not be verbose or perform long analysis.

Response style rules:
- Respond in 1–3 sentences.
- Use plain, neutral language.
- Prefer reflective phrasing (e.g., “It sounds like…”, “This seems to connect to…”).
- If something is ambiguous, say so explicitly.
- If the input is factual or logistical, acknowledge it briefly.

Interpretation guidelines:
- If the input appears to be a thought or idea, reflect it back succinctly.
- If it appears to describe a task or obligation, note that without formalizing it.
- If it appears to be a question, answer only if it is factual and self-contained.
- If it appears to be emotional or evaluative, acknowledge the sentiment without amplifying it.

You are allowed to:
- paraphrase the input
- point out patterns or themes if they are obvious from the single input
- mention uncertainty or incompleteness

You are NOT allowed to:
- suggest next steps
- optimize the user’s behavior
- challenge beliefs
- reframe goals
- escalate scope

This interaction is part of a long-term log. Assume the content will be revisited later.
Here is the content:
{text}
"""
    response = call_ollama(prompt)
    print(response)



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