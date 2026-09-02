# AutoScribe managed-vault lifecycle helpers.
# Source this file from ~/.zshrc.

typeset -g AUTOSCRIBE_CLIENT_CLI_ROOT="${${(%):-%x}:A:h:h}"

create-vault() {
  node "${AUTOSCRIBE_CLIENT_CLI_ROOT}/scripts/vault/create-vault.js" "$@"
}

update-vault() {
  node "${AUTOSCRIBE_CLIENT_CLI_ROOT}/scripts/vault/update-vault.js" "$@"
}

update-core() {
  node "${AUTOSCRIBE_CLIENT_CLI_ROOT}/scripts/vault/update-core.js" "$@"
}
