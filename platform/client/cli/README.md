# AutoScribe managed-vault CLI

This package is a small lifecycle/convenience layer for managed Obsidian vaults.
It does not implement dispatch, plan handling, content scanning, response writeback,
or background Git synchronization.

Retained commands:

- `create-vault` — install the shared Obsidian core, attach `_control`, initialize the vault Git repository, create its bare backup remote, and optionally open Obsidian.
- `update-vault` — copy the whitelisted shared `.obsidian` JSON configuration into a managed vault.
- `update-core` — copy the same whitelisted JSON configuration from a managed vault back into the shared core template.

Source `zsh/vault.zsh` for direct functions. Source `zsh/frontend.zsh` as well if the compact `cli <command>` dispatcher is useful.

All client constants are defined in `config.js`. The CLI does not read AutoScribe path configuration from shell environment variables or external config files. External paths in `config.js` are runtime targets/resources such as vault backup repositories and the Obsidian executable.
