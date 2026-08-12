# Migration boundary

## Moved to feeder

- repository status and selective content commits
- Markdown/frontmatter scanning and slug indexing
- current-selection and run-state management
- instruction and plan upload
- Pandoc processing and dispatch
- pending-response discovery and guarded response writeback
- all generated AutoScribe manifests and operational state

## Retained in this package

- managed-vault creation
- opening vaults in Obsidian
- pushing committed vault changes to their configured upstream
- synchronizing whitelisted core assets into a managed vault
- synchronizing whitelisted managed-vault assets back into core
