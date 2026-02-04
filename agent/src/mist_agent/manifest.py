"""Agent manifest: declares capabilities and widgets for broker registration."""

MANIFEST = {
    "name": "mist",
    "description": "Reflective journaling companion",
    "commands": [
        "note",
        "notes",
        "recall",
        "aggregate",
        "sync",
        "resynth",
        "synthesis",
        "persona",
        "task",
        "tasks",
        "event",
        "events",
        "topic",
        "view",
        "edit",
        "set",
        "settings",
        "status",
        "stop",
        "help",
    ],
    "widgets": [
        {
            "id": "chat",
            "module": "mist_agent.widgets.chat",
            "class_name": "MistChatPanel",
            "default": True,
        },
        {
            "id": "topics",
            "module": "mist_agent.widgets.topics",
            "class_name": "TopicsPanel",
        },
    ],
}
