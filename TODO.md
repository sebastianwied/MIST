# TODO

## Done this session

- `topic merge <source> <target>` — merge two topics: moves noteLog entries, .md notes, synthesis, and about content; deletes source
- F3 toggle between side-panel and full-screen editor views (persists preference)
- `view` opens in read-only mode; `edit` opens read-write
- `edit` command wired end-to-end (dispatch, broker sub-command, TUI save flow)
- `note new [topic] <title>` — creates `.md` in topic's `notes/` dir or `data/notes/drafts/`
- `note list <topic|drafts>` — lists note files
- Draft notes: unfiled `note new <title>` saves to `data/notes/drafts/`
- Storage helpers: `create_topic_note`, `create_draft_note`, `save_topic_note`, `save_draft_note`, etc.
- `note edit <topic|drafts> <filename>` — open existing notes in the editor
- Topics panel: shows `[id] name (slug)`, lists note files under selected topic, click to open/edit
- Broker: `list_topic_notes`, `load_topic_note`, `load_draft_note` storage actions

## Remaining: Note-Taking System

### Implement a recursive language model system 
- Want to implement RLM for the Synthesis and Resynth commands. Allow the small models I'm running to effectively handle notebases of growing size.

## Remaining: Science Agent
- Build filtering/sorting tools

## Remaining: Architecture Phase 6

### Phase 6: Remote gateway
- Add HTTP/WebSocket listener to broker for phone and multi-device access
- Thin gateway that accepts requests from mobile devices and forwards as protocol messages
- Run broker + agents on a server; TUI and other clients connect over TCP
- Protocol stays the same (JSON lines with message envelope)
