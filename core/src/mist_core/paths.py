"""Centralised path constants, parameterized by root directory.

Usage:
    paths = Paths(root=Path("data"))          # production
    paths = Paths(root=tmp_path / "data")     # tests
"""

from pathlib import Path


class Paths:
    """All MIST data paths derived from a single root directory."""

    def __init__(self, root: Path | str = Path("data")) -> None:
        self.root = Path(root)

    # ── Global paths ────────────────────────────────────────────────

    @property
    def db(self) -> Path:
        return self.root / "mist.db"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def socket_path(self) -> Path:
        return self.root / "broker" / "mist.sock"

    # ── Agent paths ─────────────────────────────────────────────────

    def agent_dir(self, agent_id: str) -> Path:
        return self.root / "agents" / agent_id

    def agent_config_dir(self, agent_id: str) -> Path:
        return self.agent_dir(agent_id) / "config"

    def agent_persona(self, agent_id: str) -> Path:
        return self.agent_config_dir(agent_id) / "persona.md"

    # ── Note storage paths (per-agent) ──────────────────────────────

    def agent_notes_dir(self, agent_id: str) -> Path:
        return self.agent_dir(agent_id) / "notes"

    def agent_note_buffer(self, agent_id: str) -> Path:
        return self.agent_notes_dir(agent_id) / "noteBuffer.jsonl"

    def agent_drafts_dir(self, agent_id: str) -> Path:
        return self.agent_notes_dir(agent_id) / "drafts"

    def agent_topics_dir(self, agent_id: str) -> Path:
        return self.agent_dir(agent_id) / "topics"

    def agent_topic_index(self, agent_id: str) -> Path:
        return self.agent_topics_dir(agent_id) / "index.json"

    def agent_topic_dir(self, agent_id: str, slug: str) -> Path:
        return self.agent_topics_dir(agent_id) / slug

    def agent_topic_note_buffer(self, agent_id: str, slug: str) -> Path:
        return self.agent_topic_dir(agent_id, slug) / "noteBuffer.jsonl"

    def agent_topic_note_feed(self, agent_id: str, slug: str) -> Path:
        return self.agent_topic_dir(agent_id, slug) / "noteFeed.md"

    def agent_topic_synthesis(self, agent_id: str, slug: str) -> Path:
        return self.agent_topic_dir(agent_id, slug) / "synthesis.md"

    # ── State paths (per-agent) ─────────────────────────────────────

    def agent_state_dir(self, agent_id: str) -> Path:
        return self.agent_dir(agent_id) / "state"

    def agent_last_aggregate(self, agent_id: str) -> Path:
        return self.agent_state_dir(agent_id) / "last_aggregate.txt"

    def agent_last_sync(self, agent_id: str) -> Path:
        return self.agent_state_dir(agent_id) / "last_sync.txt"

    # ── Helpers ─────────────────────────────────────────────────────

    def ensure_agent_dirs(self, agent_id: str) -> None:
        """Create the standard directory tree for an agent."""
        self.agent_config_dir(agent_id).mkdir(parents=True, exist_ok=True)
        self.agent_notes_dir(agent_id).mkdir(parents=True, exist_ok=True)
        self.agent_topics_dir(agent_id).mkdir(parents=True, exist_ok=True)
