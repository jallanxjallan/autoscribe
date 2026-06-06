# Obsidian / AutoScribe zsh launchers

These launchers belong inside the isolated CLI package:

```text
/home/jeremy/Autoscribe/client/cli/zsh
```

Source these from `~/.zshrc`:

```zsh
source "$HOME/Autoscribe/client/cli/zsh/frontend.zsh"
source "$HOME/Autoscribe/client/cli/zsh/vault.zsh"
source "$HOME/Autoscribe/client/cli/zsh/testing.zsh"
```

Surfaces:

- `frontend.zsh`: operations intended to become Electron UI actions.
- `vault.zsh`: Obsidian-specific operations that may be ported, replaced, or kept for Obsidian/geek-editor installations.
- `testing.zsh`: local smoke-test and ad hoc convenience commands.

All roots and command paths are declared in `config.zsh`.

There are no fallback paths, compatibility aliases, or shim variables. If the tree
moves or a command path changes, edit `config.zsh`.
