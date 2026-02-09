"""Notes agent manifest definition."""

from mist_client import ManifestBuilder

MANIFEST = (
    ManifestBuilder("notes")
    .description("Note-taking and knowledge synthesis")
    .command("note", "Save a quick note", args={"text": "str"})
    .command("notes", "List recent notes")
    .command("recall", "Search past notes via LLM", args={"query": "str"})
    .command("aggregate", "Classify new notes into topics")
    .command("sync", "Update topic synthesis with new entries")
    .command("resynth", "Full synthesis rewrite (deep model)")
    .command("synthesis", "Resynthesize a single topic", args={"topic": "str"})
    .command("topics", "List all topics")
    .command("topic", "Topic management (add, merge)", args={"action": "str"})
    .command("drafts", "List draft notes")
    .panel("chat", "Notes", "chat", default=True)
    .panel("topics", "Topics", "browser")
    .build()
)
