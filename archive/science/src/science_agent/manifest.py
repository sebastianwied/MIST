"""Agent manifest: declares capabilities and widgets for broker registration."""

AGENT_ENTRY = {
    "name": "science",
    "command": "mist-science",
    "description": "Scientific article search and library",
}

MANIFEST = {
    "name": "science",
    "description": "Scientific article search and library",
    "commands": [
        "search",
        "review",
        "import",
        "articles",
        "article",
        "tag",
        "tags",
        "pdf",
        "help",
    ],
    "widgets": [
        {
            "id": "library",
            "module": "science_agent.widgets.library",
            "class_name": "ScienceLibraryPanel",
            "default": True,
        },
    ],
}
