"""One-time migration: frontmatter rawLog → JSONL, flat synthesis → per-topic dirs."""

import re
import shutil
from pathlib import Path

from mist_core.storage import (
    ARCHIVE_PATH,
    LAST_AGGREGATE_PATH,
    RAWLOG_PATH,
    TOPICS_DIR,
    TopicInfo,
    _entry_to_jsonl,
    RawLogEntry,
    save_topic_index,
)
from .synthesis import _slugify

_OLD_RAWLOG = Path("data/notes/rawLog.md")
_OLD_ARCHIVE = Path("data/notes/rawLog_archive.md")
_OLD_SYNTHESIS_DIR = Path("data/synthesis")
_OLD_LAST_SUMMARIZED = Path("data/state/last_summarized.txt")

_ENTRY_RE = re.compile(
    r"---\s*\ntime:\s*([^\n]+)\nsource:\s*([^\n]+)\n---\s*\n(.*?)(?=\n---\s*\ntime:|\Z)",
    re.DOTALL,
)

_HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def _parse_frontmatter_file(path: Path) -> list[RawLogEntry]:
    """Parse an old frontmatter-format rawLog file."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    entries = []
    for m in _ENTRY_RE.finditer(content):
        entries.append(RawLogEntry(
            time=m.group(1).strip(),
            source=m.group(2).strip(),
            text=m.group(3).strip(),
        ))
    return entries


def _write_jsonl(path: Path, entries: list[RawLogEntry]) -> None:
    """Write entries as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(_entry_to_jsonl(e) + "\n")


def _backup(path: Path) -> None:
    """Rename a file to .bak if it exists."""
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            shutil.move(str(path), str(bak))
            print(f"  Backed up: {path} → {bak}")


def migrate() -> None:
    """Run all migration steps."""
    print("MIST data migration: frontmatter → JSONL + per-topic dirs\n")

    # 1. Convert rawLog.md → rawLog.jsonl
    if _OLD_RAWLOG.exists() and not RAWLOG_PATH.exists():
        entries = _parse_frontmatter_file(_OLD_RAWLOG)
        _write_jsonl(RAWLOG_PATH, entries)
        print(f"  Converted rawLog.md → rawLog.jsonl ({len(entries)} entries)")
        _backup(_OLD_RAWLOG)
    else:
        print("  rawLog: skipped (already migrated or no source)")

    # 2. Convert rawLog_archive.md → archive.jsonl
    if _OLD_ARCHIVE.exists() and not ARCHIVE_PATH.exists():
        entries = _parse_frontmatter_file(_OLD_ARCHIVE)
        _write_jsonl(ARCHIVE_PATH, entries)
        print(f"  Converted rawLog_archive.md → archive.jsonl ({len(entries)} entries)")
        _backup(_OLD_ARCHIVE)
    else:
        print("  archive: skipped (already migrated or no source)")

    # 3. Convert synthesis/*.md → topics/<slug>/synthesis.md + noteLog.jsonl
    topic_infos: list[TopicInfo] = []
    if _OLD_SYNTHESIS_DIR.exists():
        topic_id = 0
        for md_path in sorted(_OLD_SYNTHESIS_DIR.glob("*.md")):
            if md_path.name == "context.md":
                continue

            content = md_path.read_text(encoding="utf-8").strip()
            if not content:
                continue

            # Extract proper name from ## heading if present
            heading_match = _HEADING_RE.search(content)
            if heading_match:
                name = heading_match.group(1).strip()
            else:
                name = md_path.stem.replace("-", " ").title()

            slug = _slugify(name)
            if not slug:
                continue

            topic_id += 1
            topic_dir = TOPICS_DIR / slug

            if not topic_dir.exists():
                topic_dir.mkdir(parents=True, exist_ok=True)
                (topic_dir / "synthesis.md").write_text(content + "\n", encoding="utf-8")
                (topic_dir / "noteLog.jsonl").write_text("", encoding="utf-8")
                print(f"  Created topic: {slug} ({name})")

                topic_infos.append(TopicInfo(
                    id=topic_id,
                    name=name,
                    slug=slug,
                    created="migrated",
                ))
                _backup(md_path)

        # 4. Build index.json
        if topic_infos:
            save_topic_index(topic_infos)
            print(f"  Created topics/index.json ({len(topic_infos)} topics)")

    # 5. Copy last_summarized.txt → last_aggregate.txt
    if _OLD_LAST_SUMMARIZED.exists() and not LAST_AGGREGATE_PATH.exists():
        LAST_AGGREGATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_OLD_LAST_SUMMARIZED), str(LAST_AGGREGATE_PATH))
        print("  Copied last_summarized.txt → last_aggregate.txt")

    print("\nMigration complete.")


def migrate_model_conf() -> None:
    """Copy model.conf / deep_model.conf values into settings.json (idempotent).

    - If model.conf exists and settings.model is empty → copy value to settings.
    - If deep_model.conf exists and model_resynth/model_synthesis are empty → copy.
    """
    from mist_core.settings import MODEL_PATH, get_setting, set_setting

    # model.conf → settings.model
    try:
        name = MODEL_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        name = ""
    if name and not get_setting("model"):
        set_setting("model", name)

    # deep_model.conf → model_resynth / model_synthesis
    deep_path = Path("data/config/deep_model.conf")
    try:
        deep_name = deep_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        deep_name = ""
    if deep_name:
        if not get_setting("model_resynth"):
            set_setting("model_resynth", deep_name)
        if not get_setting("model_synthesis"):
            set_setting("model_synthesis", deep_name)


if __name__ == "__main__":
    migrate()
