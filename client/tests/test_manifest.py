"""Tests for mist_client.manifest."""

from mist_client.manifest import ManifestBuilder


class TestManifestBuilder:
    def test_basic(self):
        m = ManifestBuilder("notes").build()
        assert m["name"] == "notes"
        assert m["description"] == ""
        assert m["commands"] == []
        assert m["panels"] == []

    def test_description(self):
        m = ManifestBuilder("notes").description("Note-taking agent").build()
        assert m["description"] == "Note-taking agent"

    def test_commands(self):
        m = (ManifestBuilder("notes")
             .command("note", "Save a note")
             .command("recall", "Recall notes", args={"query": "str"})
             .build())
        assert len(m["commands"]) == 2
        assert m["commands"][0]["name"] == "note"
        assert m["commands"][0]["description"] == "Save a note"
        assert "args" not in m["commands"][0]
        assert m["commands"][1]["args"] == {"query": "str"}

    def test_panels(self):
        m = (ManifestBuilder("notes")
             .panel("chat", "Notes", "chat", default=True)
             .panel("topics", "Topics", "browser")
             .build())
        assert len(m["panels"]) == 2
        assert m["panels"][0]["id"] == "chat"
        assert m["panels"][0]["default"] is True
        assert "default" not in m["panels"][1]

    def test_fluent_chaining(self):
        m = (ManifestBuilder("science")
             .description("Science agent")
             .command("search", "Search papers")
             .command("import", "Import a paper")
             .panel("chat", "Science", "chat", default=True)
             .panel("library", "Library", "browser")
             .build())
        assert m["name"] == "science"
        assert len(m["commands"]) == 2
        assert len(m["panels"]) == 2
