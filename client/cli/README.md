# Obsidian vault CLI

This package now contains only operations that manage the Obsidian vault
itself or its Git remote:

- `create-vault`
- `open-vault`
- `push-vault`
- `update-vault`
- `update-core`

AutoScribe content scanning, selection, uploads, plan handling, dispatch,
writeback, and generated-state maintenance have moved to the Python `feeder`
package. Use `obs` or the Obsidian control-panel IPC bridge for those tasks.

Source `zsh/vault.zsh` for the direct command functions, or
`zsh/frontend.zsh` for the compact `cli <command>` dispatcher.
