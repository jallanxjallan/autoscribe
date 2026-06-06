# cli/zsh/common.zsh
# Shared zsh dispatch helpers for the AutoScribe client package.
#
# This file is intentionally re-sourceable. During active development, shells
# often keep older helper definitions alive; returning early from a loaded guard
# can leave frontend/vault functions calling helpers that no longer exist.

# Identify this source file without using any external package assumptions.
typeset -g _OBSIDIAN_ZSH_COMMON_LOADED="2026-06-06-resourceable"
typeset -g _OBSIDIAN_ZSH_DIR="${${(%):-%x}:A:h}"

_obsidian_zsh_error() {
  emulate -L zsh
  print -u2 -- "ERROR: $*"
}

_obsidian_source_launcher_env() {
  emulate -L zsh
  setopt local_options no_unset

  local env_path="$_OBSIDIAN_ZSH_DIR/config.zsh"

  if [[ ! -r "$env_path" ]]; then
    _obsidian_zsh_error "launcher config not readable: $env_path"
    return 78
  fi

  source "$env_path"

  local required_dirs=(
    "$AUTOSCRIBE_CLIENT_ROOT"
    "$OBSIDIAN_CLI_ROOT"
    "$OBSIDIAN_TOOLS_ROOT"
    "$OBSIDIAN_CONTROL_ROOT"
  )
  local dir
  for dir in "${required_dirs[@]}"; do
    if [[ ! -d "$dir" ]]; then
      _obsidian_zsh_error "required directory not found: $dir"
      return 78
    fi
  done
}

_obsidian_source_launcher_env || return $?

_obsidian_command_exists() {
  emulate -L zsh
  setopt local_options no_unset

  if (( $# != 1 )); then
    _obsidian_zsh_error "_obsidian_command_exists requires exactly one command"
    return 64
  fi

  command -v "$1" >/dev/null 2>&1
}

_obsidian_script_path() {
  emulate -L zsh
  setopt local_options no_unset

  if (( $# != 1 )); then
    _obsidian_zsh_error "_obsidian_script_path requires exactly one script-relative path"
    return 64
  fi

  local script_rel="$1"
  print -- "$OBSIDIAN_CLI_ROOT/scripts/${script_rel}.js"
}

_obsidian_node_script() {
  emulate -L zsh
  setopt local_options no_unset pipe_fail

  if (( $# < 1 )); then
    _obsidian_zsh_error "_obsidian_node_script requires a script-relative path"
    return 64
  fi

  local script_rel="$1"
  shift

  local script_path
  script_path="$(_obsidian_script_path "$script_rel")" || return $?

  if [[ ! -f "$script_path" ]]; then
    _obsidian_zsh_error "Node script not found: $script_path"
    return 127
  fi

  if ! _obsidian_command_exists "$OBSIDIAN_NODE_BIN"; then
    _obsidian_zsh_error "Node executable not found: $OBSIDIAN_NODE_BIN"
    return 127
  fi

  command "$OBSIDIAN_NODE_BIN" "$script_path" "$@"
}

_obsidian_asc() {
  emulate -L zsh
  setopt local_options no_unset pipe_fail

  if ! _obsidian_command_exists "$ASC_BIN"; then
    _obsidian_zsh_error "asc executable not found: $ASC_BIN"
    return 127
  fi

  command "$ASC_BIN" "$@"
}

_obsidian_redis_cli() {
  emulate -L zsh
  setopt local_options no_unset pipe_fail

  if ! _obsidian_command_exists "$REDIS_CLI_BIN"; then
    _obsidian_zsh_error "redis-cli executable not found: $REDIS_CLI_BIN"
    return 127
  fi

  command "$REDIS_CLI_BIN" "$@"
}

_obsidian_define_node_function() {
  emulate -L zsh
  setopt local_options no_unset

  if (( $# != 2 )); then
    _obsidian_zsh_error "_obsidian_define_node_function requires a public name and script-relative path"
    return 64
  fi

  local public_name="$1"
  local script_rel="$2"

  eval "${public_name}() { _obsidian_node_script '${script_rel}' \"\$@\" }"
}

_obsidian_define_node_functions() {
  emulate -L zsh
  setopt local_options no_unset

  local spec public_name script_rel

  for spec in "$@"; do
    public_name="${spec%%:*}"
    script_rel="${spec#*:}"

    if [[ -z "$public_name" || -z "$script_rel" || "$public_name" == "$script_rel" ]]; then
      _obsidian_zsh_error "bad command spec: $spec"
      return 64
    fi

    _obsidian_define_node_function "$public_name" "$script_rel" || return $?
  done
}

obsidian-cli-version() {
  emulate -L zsh
  print -- "$OBSIDIAN_CLI_VERSION"
}

obsidian-cli-config() {
  emulate -L zsh
  cat <<EOF_CONFIG
OBSIDIAN_ZSH_DIR=$_OBSIDIAN_ZSH_DIR
AUTOSCRIBE_CLIENT_ROOT=$AUTOSCRIBE_CLIENT_ROOT
OBSIDIAN_CLI_ROOT=$OBSIDIAN_CLI_ROOT
OBSIDIAN_TOOLS_ROOT=$OBSIDIAN_TOOLS_ROOT
OBSIDIAN_CONTROL_ROOT=$OBSIDIAN_CONTROL_ROOT
OBSIDIAN_CORE_ROOT=$OBSIDIAN_CORE_ROOT
OBSIDIAN_GLOBAL_INSTRUCTIONS=$OBSIDIAN_GLOBAL_INSTRUCTIONS
AUTOSCRIBE_HOME=$AUTOSCRIBE_HOME
AUTOSCRIBE_DATA_ROOT=$AUTOSCRIBE_DATA_ROOT
ASC_BIN=$ASC_BIN
OBSIDIAN_NODE_BIN=$OBSIDIAN_NODE_BIN
OBSIDIAN_APP_BIN=$OBSIDIAN_APP_BIN
OBSIDIAN_GIT_BIN=$OBSIDIAN_GIT_BIN
OBSIDIAN_RG_BIN=$OBSIDIAN_RG_BIN
OBSIDIAN_PANDOC_BIN=$OBSIDIAN_PANDOC_BIN
OBSIDIAN_PANDOC_DATA_DIR=$OBSIDIAN_PANDOC_DATA_DIR
OBSIDIAN_OPEN_BIN=$OBSIDIAN_OPEN_BIN
OBSIDIAN_SHELL_BIN=$OBSIDIAN_SHELL_BIN
REDIS_CLI_BIN=$REDIS_CLI_BIN
EOF_CONFIG
}
