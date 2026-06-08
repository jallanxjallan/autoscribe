# cli/zsh/vault.zsh
# Obsidian-specific shell surface.
#
# These functions are for workflows that depend on Obsidian itself, the
# Obsidian app launcher, Obsidian vault layout conventions, or template-vault
# update behavior. They are not the future Electron frontend surface.

_OBSIDIAN_VAULT_SURFACE_DIR="${${(%):-%x}:A:h}"
source "$_OBSIDIAN_VAULT_SURFACE_DIR/common.zsh" || return $?

_vault_find_root_from_cwd() {
  emulate -L zsh
  setopt local_options no_unset

  local dir="${PWD:A}"

  while [[ -n "$dir" ]]; do
    if [[ -d "$dir/.obsidian" ]]; then
      print -r -- "$dir"
      return 0
    fi

    [[ "$dir" == "/" ]] && break
    dir="${dir:h}"
  done

  return 1
}

_vault_node_script() {
  emulate -L zsh
  setopt local_options no_unset pipe_fail

  local vault_root

  if ! vault_root="$(_vault_find_root_from_cwd)"; then
    print -u2 -- "ERROR: Current directory is not inside an Obsidian vault: ${PWD}"
    return 1
  fi

  OBSIDIAN_VAULT_ROOT="$vault_root" _obsidian_node_script "$@"
}

create-vault() {
  emulate -L zsh
  _obsidian_node_script "vault/create-vault" "$@"
}

open-vault() {
  emulate -L zsh
  _vault_node_script "obsidian/open-vault" "$@"
}

push-vault() {
  emulate -L zsh
  _vault_node_script "git/push-vault" "$@"
}

update-vault() {
  emulate -L zsh
  _vault_node_script "vault/update-vault" "$@"
}

update-core() {
  emulate -L zsh
  _vault_node_script "vault/update-core" "$@"
}

reset-manifests() {
  emulate -L zsh
  _vault_node_script "maintenance/reset-manifests" "$@"
}

obsidian-vault-help() {
  emulate -L zsh
  cat <<'EOF_HELP'
Obsidian vault commands:

  create-vault     Initialize a new managed Obsidian vault from the control/template assets
  open-vault       Open the active or selected vault in Obsidian
  push-vault       Push committed vault changes to the configured vault remote
  update-vault     Update an Obsidian vault from the template/control assets
  update-core      Update shared core/control assets
  reset-manifests  Reset generated selection/run manifests for the active vault

These commands are Obsidian-specific and are separate from frontend.zsh.
EOF_HELP
}
