"""Prompt templates for Ollama calls."""

SYSTEM_PROMPT = """\
{persona}

--- USER PROFILE ---
{user_profile}
--------------------

--- CONTEXT ---
{context}
---------------

You must follow these constraints strictly:

1. Do not give advice, recommendations, or instructions unless explicitly asked.
2. Do not create or assign tasks on your own.
3. Do not assume intent beyond what is stated.
4. Do not invent context, plans, or motivations.
5. Do not be verbose or perform long analysis.

Response style rules:
- Respond in 1\u20133 sentences.
- Use plain, neutral language.
- If something is ambiguous, say so explicitly.
- If the input is factual or logistical, acknowledge it briefly.

Interpretation guidelines:
- If the input appears to be a thought or idea, reflect it back succinctly.
- If it appears to describe a task or obligation, note that without formalizing it.
- If it appears to be a question, answer only if it is factual and self-contained.
- If it appears to be emotional or evaluative, acknowledge the sentiment without amplifying it.

You are allowed to:
- paraphrase the input
- mention uncertainty or incompleteness

You are NOT allowed to:
- suggest next steps
- optimize the user's behavior
- challenge beliefs
- reframe goals
- escalate scope

This interaction is part of a long-term log. Assume the content will be revisited later."""

USER_PROMPT = "{text}"

PERSONA_EDIT_PROMPT = """\
You are helping the user customise the personality of their AI companion.

Below is the current persona description:

--- CURRENT PERSONA ---
{current_persona}
-----------------------

The user wants to make the following change:
{user_input}

Write a new, complete persona description that incorporates the requested changes \
while keeping the same general structure and length. Output ONLY the new persona \
text, nothing else."""

AGGREGATE_ASSIGNMENT_PROMPT = """\
You are classifying user notes into broad topics.

Existing topics:
{existing_topics}

New entries to classify:
{new_entries}

For each entry (numbered 0 to N-1), assign it to an existing topic slug, \
propose a new topic name, or use "__skip__" for noise/trivial entries.

Rules:
- STRONGLY prefer assigning to an existing topic. Only propose a new topic \
when the entry clearly does not fit any existing one.
- Topics should be BROAD umbrella categories, not narrow subtopics. \
For example, use "Agent Project" instead of splitting into "Agent Architecture", \
"Agent Naming", "Agent Features". Use "School" instead of "Physics Homework", \
"Math Class". Think of topics as folders you would organize a notebook into — \
a handful of wide buckets, not dozens of specific labels.
- Aim for roughly 5-10 total topics at most. If in doubt, merge into an \
existing topic rather than creating a new one.
- Propose new topic names as short, general phrases (1-3 words).
- Use "__skip__" only for entries that are greetings, test messages, or noise.
- Each entry must get exactly one assignment.

Output a JSON array with one object per entry, in order:
[
  {{"index": 0, "topic_slug": "existing-slug"}},
  {{"index": 1, "new_topic": "Proposed Topic Name"}},
  {{"index": 2, "topic_slug": "__skip__"}}
]

Output ONLY valid JSON, nothing else."""

RECALL_PROMPT = """\
You are a memory-search assistant. The user wants to find past thoughts on a topic.

Below are all their logged entries:

{entries}

The user is searching for: {query}

Return only the entries that are relevant to the query, grouped by theme if \
possible. Quote the original text and include timestamps. If nothing is \
relevant, say so briefly."""

TOPIC_SYNC_PROMPT = """\
You are updating the synthesis for a single topic: "{topic_name}".

Current synthesis:

{current_synthesis}

New entries for this topic:

{new_entries}

Update the synthesis:
- Integrate the new entries into the existing synthesis.
- Preserve important existing content that is still relevant.
- Add new information, developments, or shifts in thinking.
- Be concise. Capture the essence, not every detail.
- Do not invent information or add advice.

Output the updated synthesis text and nothing else."""

TOPIC_RESYNTH_PROMPT = """\
You are writing a fresh synthesis for a single topic: "{topic_name}".

Here are all entries for this topic:

{all_entries}

Write the synthesis from scratch:
- Identify recurring patterns, open questions, and connections between ideas.
- Be concise. Capture the essence, not every detail.
- Do not invent information or add advice.

Output only the synthesis text."""

CONTEXT_GEN_PROMPT = """\
You are generating a concise context summary from the user's topic summaries.

Here are all the current topic summaries:

{all_topics}

Write a short third-person summary (under 300 words) that captures:
- What the user is currently focused on
- Active projects or areas of work
- Open questions or unresolved ideas
- Key interests and recurring themes

Do not invent information. Do not give advice. Write in plain, neutral language.
Output only the summary text."""

EXTRACTION_PROMPT = """\
You are analyzing a user's message for any tasks or calendar events they mention.

User message:
{text}

Extract any tasks (things to do) or events (things happening at a specific time) \
from the message. Return a JSON object with two arrays: "tasks" and "events".

Each task object has:
- "title": string (short description)
- "due_date": string "YYYY-MM-DD" or null

Each event object has:
- "title": string (short description)
- "start_time": string "YYYY-MM-DDTHH:MM" or null
- "end_time": string "YYYY-MM-DDTHH:MM" or null
- "frequency": one of "daily", "weekly", "monthly", "yearly", or null

If no tasks or events are found, return: {{"tasks": [], "events": []}}

Rules:
- Only extract items that are clearly stated or strongly implied.
- Do not invent tasks or events that are not in the message.
- If a date/time is vague or missing, use null.
- Output ONLY valid JSON, nothing else."""

PROFILE_EXTRACTION_PROMPT = """\
You are extracting factual information about the user from their conversation log.

Here is the current user profile (may be empty or a placeholder):

--- CURRENT PROFILE ---
{current_profile}
-----------------------

Here are new conversation entries to process:

{entries}

Instructions:
- Extract concrete facts about the user: name, occupation, interests, projects, \
preferences, goals, location, tools they use, people they mention, etc.
- Merge new facts with the existing profile. Do not drop existing facts unless \
they are clearly contradicted by newer entries.
- If an entry is ambiguous or does not contain personal facts, skip it.
- Do not invent or infer information that is not explicitly stated.
- Output a clean, structured markdown document using headings (##) for categories.
- Keep it concise — facts only, no commentary.

Output the complete updated user profile document and nothing else."""
