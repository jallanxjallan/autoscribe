# Obsidian / AutoScribe zsh launchers

These launchers belong inside the isolated CLI package:

```text
/home/jeremy/Work/AutoScribe/platform/client/cli/zsh
```

Source these from `~/.zshrc`:

```zsh
export WORK_ROOT="$HOME/Work"
export AUTOSCRIBE_ROOT="$WORK_ROOT/AutoScribe"
export AUTOSCRIBE_PLATFORM="$AUTOSCRIBE_ROOT/platform"
export AUTOSCRIBE_INSTRUCTIONS="$AUTOSCRIBE_ROOT/instructions"

source "$AUTOSCRIBE_PLATFORM/client/cli/zsh/frontend.zsh"
source "$AUTOSCRIBE_PLATFORM/client/cli/zsh/vault.zsh"
```

Surfaces:

- `frontend.zsh`: operations intended to become Electron UI actions.
- `vault.zsh`: Obsidian-specific operations that may be ported, replaced, or kept for Obsidian/geek-editor installations.
- `config.zsh`: derives launcher paths from the work-tree roots, with defaults
  for shells that have not already declared them.

The normal source of truth for the work-tree roots is `~/.zshrc`. If the tree
moves, update that root block rather than editing every launcher.
