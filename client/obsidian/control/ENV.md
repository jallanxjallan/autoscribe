# Environment variables

The control package does not use a shared config module. External command paths should be provided through environment variables when Obsidian is launched.

Recommended:

```zsh
export ASC_BIN=/home/jeremy/Python3.13Env/bin/asc
export OBSIDIAN_CONTROL_ROOT=/home/jeremy/Autoscribe/client/obsidian/control
export OBSIDIAN_GIT_BIN=/usr/bin/git
export OBSIDIAN_SHELL_BIN=/usr/bin/bash
export OBSIDIAN_OPEN_BIN=/usr/bin/xdg-open
export OBSIDIAN_RG_BIN=/usr/bin/rg
export AUTOSCRIBE_HOME=$HOME/.local/share/autoscribe
```

Compatibility aliases currently recognized:

- `_AUTOSCRIBE_ASC_BIN` as an alias for `ASC_BIN`
- `_OBSIDIAN_GIT_BIN` as an alias for `OBSIDIAN_GIT_BIN`
- `_OBSIDIAN_CONTROL_ROOT` as an alias for `OBSIDIAN_CONTROL_ROOT`
- `AUTOSCRIBE_DATA_ROOT` as an alias for `AUTOSCRIBE_HOME`

Package-root discovery is local and relative: `_control` finds its own `scripts/` and `scripts/lib/` folders through the active query path or `__dirname`.
