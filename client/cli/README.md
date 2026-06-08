# cli package

Node-side helpers and command implementations for shell/Electron-facing Obsidian workflows.

This package is deliberately isolated from `control/`. Do not require files from `control/` here.
External command paths are read from environment variables, not from a shared config module.

## Current public command surface

Vault commands:

- `create-vault`
- `open-vault`
- `update-vault`
- `update-core`
- `push-vault`

AutoScribe commands:

- `upload-instructions`
- `upload-plans`
- `upload-prompts`
- `writeback`
- `writenew`

Stale legacy command wrappers have been removed from this tree; the supported command surface is the list above.

