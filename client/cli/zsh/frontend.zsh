# cli/zsh/frontend.zsh
# Retained vault-lifecycle command surface.
#
# Source this from ~/.zshrc when the compact `cli <command>` dispatcher is
# preferred. Direct functions are also available from vault.zsh.

_OBSIDIAN_FRONTEND_SURFACE_DIR="${${(%):-%x}:A:h}"
source "$_OBSIDIAN_FRONTEND_SURFACE_DIR/common.zsh" || return $?

_OBSIDIAN_FRONTEND_COMMANDS=(
  'create-vault:vault/create-vault'
  'open-vault:obsidian/open-vault'
  'push-vault:git/push-vault'
  'update-vault:vault/update-vault'
  'update-core:vault/update-core'
)

_obsidian_define_node_functions "${_OBSIDIAN_FRONTEND_COMMANDS[@]}" || return $?


cli() {
  emulate -L zsh
  setopt local_options no_unset

  if (( $# == 0 )); then
    frontend-help
    return 0
  fi

  local command_name="$1"
  shift

  case "$command_name" in
    create-vault|open-vault|push-vault|update-vault|update-core)
      "$command_name" "$@"
      ;;
    config)
      obsidian-cli-config "$@"
      ;;
    version)
      obsidian-cli-version "$@"
      ;;
    help|-h|--help)
      frontend-help
      ;;
    *)
      _obsidian_zsh_error "unknown cli command: $command_name"
      frontend-help
      return 64
      ;;
  esac
}

frontend-help() {
  emulate -L zsh
  cat <<'HELP'
Obsidian vault command surface

Vault lifecycle:
  create-vault <path>             Create and initialize a managed vault
  open-vault [path]               Open a vault in Obsidian
  push-vault [path]               Push committed vault changes upstream
  update-vault [options] [path]   Copy managed core assets into a vault
  update-core [options] [path]    Copy managed vault assets back into core

Diagnostics:
  obsidian-cli-version            Print CLI surface version
  obsidian-cli-config             Print active launcher environment values
  cli <command> [args...]         Dispatch one of the retained commands
  frontend-help                   Show this help

AutoScribe upload, dispatch, scanning, selection and response-writeback
operations are provided by the Python feeder through `obs` and Obsidian IPC.
HELP
}
