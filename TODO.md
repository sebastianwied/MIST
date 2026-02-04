# TODO

## Done this session

- F3 toggle between side-panel and full-screen editor views (persists preference)
- `view` opens in read-only mode; `edit` opens read-write
- `edit` command wired end-to-end (dispatch, broker sub-command, TUI save flow)
- `note new [topic] <title>` — creates `.md` in topic's `notes/` dir or `data/notes/drafts/`
- `note list <topic|drafts>` — lists note files
- Draft notes: unfiled `note new <title>` saves to `data/notes/drafts/`
- Storage helpers: `create_topic_note`, `create_draft_note`, `save_topic_note`, `save_draft_note`, etc.

## Remaining: Note-Taking System

### Open/edit existing notes
- `note open <topic> <filename>` or `note open <filename>` (for drafts) — open an existing note in the editor
- Browse and open notes from the Topics panel widget

### Promote from noteLog
- `note promote <topic> <entry-index> [outline|draft|deep]` — expand a noteLog entry into a standalone `.md` via LLM
- Three depth levels: outline (bullets), draft (paragraphs), deep (analysis with `[[wiki-links]]`)
- Requires LLM prompts in `prompts.py`

### Synthesis changes
- Update `sync` / `resynth` / `synthesis` to read `.md` files from `notes/` alongside `noteLog.jsonl`
- Both feed into the same LLM prompts as equal input

### Cross-linking
- Support `[[topic/note-name]]` wiki-style links in notes
- LLM suggests connections during promotion (especially deep level) and synthesis

### Filing drafts
- Command to move a draft into a topic's `notes/` directory (e.g. `note file <filename> <topic>`)

### Topics panel integration
- Show note files under each topic in the topics widget
- Click to open in side-panel or full-screen editor

## Remaining: Architecture Phase 6

### Phase 6: Remote gateway
- Add HTTP/WebSocket listener to broker for phone and multi-device access
- Thin gateway that accepts requests from mobile devices and forwards as protocol messages
- Run broker + agents on a server; TUI and other clients connect over TCP
- Protocol stays the same (JSON lines with message envelope)
