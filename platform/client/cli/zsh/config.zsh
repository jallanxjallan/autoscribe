# cli/zsh/config.zsh
# AutoScribe client launcher environment.
#
# The main work-tree roots normally come from ~/.zshrc. Defaults keep these
# launchers usable when they are sourced independently.

export OBSIDIAN_CLI_VERSION="2026-06-08-current"

# Work-tree and package roots.
export WORK_ROOT="${WORK_ROOT:-$HOME/Work}"
export AUTOSCRIBE_ROOT="${AUTOSCRIBE_ROOT:-$WORK_ROOT/AutoScribe}"
export AUTOSCRIBE_PLATFORM="${AUTOSCRIBE_PLATFORM:-$AUTOSCRIBE_ROOT/platform}"
export AUTOSCRIBE_INSTRUCTIONS="${AUTOSCRIBE_INSTRUCTIONS:-$AUTOSCRIBE_PLATFORM/instructions}"
export AUTOSCRIBE_EXTENSIONS_ROOT="${AUTOSCRIBE_EXTENSIONS_ROOT:-$AUTOSCRIBE_PLATFORM/extensions}"
export AUTOSCRIBE_CLIENT_ROOT="$AUTOSCRIBE_PLATFORM/client"
export OBSIDIAN_CLI_ROOT="$AUTOSCRIBE_CLIENT_ROOT/cli"
export OBSIDIAN_TOOLS_ROOT="$AUTOSCRIBE_CLIENT_ROOT/obsidian"
export OBSIDIAN_CONTROL_ROOT="$OBSIDIAN_TOOLS_ROOT/control"
export OBSIDIAN_CORE_ROOT="$OBSIDIAN_TOOLS_ROOT/core"
export OBSIDIAN_PANDOC_DATA_DIR="$AUTOSCRIBE_CLIENT_ROOT/extensions"
export OBSIDIAN_GLOBAL_INSTRUCTIONS="$AUTOSCRIBE_INSTRUCTIONS"

# Local operation/state root for global client cache only. Vault-specific
# selections and manifests live inside <vault>/.autoscribe.
export AUTOSCRIBE_HOME="$HOME/.local/share/autoscribe"
export AUTOSCRIBE_DATA_ROOT="$AUTOSCRIBE_HOME"

# External commands.
export ASC_BIN="$HOME/Python3.13Env/bin/asc"
export OBSIDIAN_NODE_BIN="node"
export OBSIDIAN_APP_BIN="obsidian"
export OBSIDIAN_GIT_BIN="git"
export OBSIDIAN_RG_BIN="rg"
export OBSIDIAN_PANDOC_BIN="pandoc"
export OBSIDIAN_OPEN_BIN="xdg-open"
export OBSIDIAN_SHELL_BIN="bash"
export REDIS_CLI_BIN="redis-cli"

# QuickAdd command IDs.
export OBSIDIAN_QA_UPDATE_IMAGES="quickadd:choice:a3f7f72f-5f31-4daa-9f42-8dfdb3fdd5d8"
export OBSIDIAN_QA_CREATE_NOTE="quickadd:choice:d4f2869c-c4f7-4892-8f89-74bc6f5dd78f"
export OBSIDIAN_QA_OPEN_DASHBOARD="quickadd:choice:caebd934-84e0-43ed-bcfe-c9a2d44231f0"
export OBSIDIAN_QA_APPLY_TEMPLATE="quickadd:choice:e6de869d-4698-45a6-a74a-b8fd02ed7efb"
