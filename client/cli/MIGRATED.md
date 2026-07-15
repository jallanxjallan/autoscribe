# Migration boundary

Moved to feeder:

- Git status, selective commits and repository state
- Markdown/frontmatter scanning and slug indexing
- instruction catalog merging active-vault, Library-vault and pipeline records
- single-instruction Pandoc upload
- registry/control snapshots
- pipeline-only plan list/load/save/delete requests
- dispatch and result writeback workflows

Retained in Obsidian:

- Dataview rendering and DOM code
- workspace/tab behavior
- Obsidian wikilink and `obsidian://` resolution
- creation of resolved temporary Markdown and metadata files
- synchronous calls through `control/scripts/lib/feeder-ipc.js`
