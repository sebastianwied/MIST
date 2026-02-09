"""Prompt templates for the notes agent."""

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
- Topics should be BROAD umbrella categories, not narrow subtopics.
- Aim for roughly 5-10 total topics at most.
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

Long-form notes for this topic:

{notes}

Update the synthesis:
- Integrate the new entries into the existing synthesis.
- Incorporate insights from the long-form notes alongside the log entries.
- Preserve important existing content that is still relevant.
- Add new information, developments, or shifts in thinking.
- Use [[topic-slug]] to reference other topics when relevant.
- Be concise. Capture the essence, not every detail.
- Do not invent information or add advice.

Output the updated synthesis text and nothing else."""

TOPIC_RESYNTH_PROMPT = """\
You are writing a fresh synthesis for a single topic: "{topic_name}".

Here are all entries for this topic:

{all_entries}

Long-form notes for this topic:

{notes}

Write the synthesis from scratch:
- Identify recurring patterns, open questions, and connections between ideas.
- Incorporate insights from the long-form notes alongside the log entries.
- Use [[topic-slug]] to reference other topics when relevant.
- Be concise. Capture the essence, not every detail.
- Do not invent information or add advice.

Output only the synthesis text."""
