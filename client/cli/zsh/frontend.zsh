# cli/zsh/frontend.zsh
# Future frontend / Electron command surface.
#
# Source this from ~/.zshrc for operations that should eventually become
# Electron UI actions. These functions are thin dispatchers into cli/scripts.

_OBSIDIAN_FRONTEND_SURFACE_DIR="${${(%):-%x}:A:h}"
source "$_OBSIDIAN_FRONTEND_SURFACE_DIR/common.zsh" || return $?

_OBSIDIAN_FRONTEND_COMMANDS=(
  'create-vault:vault/create-vault'
  'upload-instructions:uploading/upload-instructions'
  'upload-plans:uploading/upload-plans'
  'upload-prompts:uploading/upload-prompts'

  'writeback:writing/writeback'
  'writenew:writing/writenew'
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
    create-vault|upload-instructions|upload-plans|upload-prompts|writeback|writenew)
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
Frontend / future Electron command surface

Vault creation:
  create-vault <path>             Create a managed vault from the control/template assets

AutoScribe upload/enqueue:
  upload-instructions             Upload dirty ins/gbl/cxt/spc files as NDJSON
  upload-plans                    Upload dirty plan.* files as NDJSON
  upload-prompts                  Emit selected run-manifest prompt records as NDJSON

AutoScribe result writing:
  writeback                       Replace bodies of matching existing vault files
  writenew [target-dir]           Write provisional results as new Markdown files

Diagnostics:
  obsidian-cli-version            Print CLI surface version
  obsidian-cli-config             Print active launcher env values
  cli <command> [args...]         Dispatch frontend commands without hitting /usr/bin/cli
  frontend-help                   Show this help

Notes:
  Command paths and roots are declared in cli/zsh/config.zsh. No fallback paths
  or compatibility aliases are provided.
HELP
}
