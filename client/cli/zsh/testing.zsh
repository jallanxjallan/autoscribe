# cli/zsh/testing.zsh
# Personal/ad hoc testing helpers.
#
# These are intentionally not part of the future frontend surface. They are
# convenience macros for Jeremy's local development and smoke tests.

_OBSIDIAN_TESTING_SURFACE_DIR="${${(%):-%x}:A:h}"
source "$_OBSIDIAN_TESTING_SURFACE_DIR/common.zsh" || return $?

run-uploads() {
  emulate -L zsh
  setopt local_options pipe_fail no_unset

  _obsidian_redis_cli flushall || return $?

  _obsidian_node_script 'uploading/enqueue-job' --allow-stale-manifest || return $?
}

run-uploads-no-reset() {
  emulate -L zsh
  setopt local_options pipe_fail no_unset

  _obsidian_node_script 'uploading/enqueue-job' --allow-stale-manifest || return $?
}

testing-help() {
  emulate -L zsh
  cat <<'HELP'
Personal testing helpers

Smoke tests:
  run-uploads                     FLUSHALL, upload stale local controls, enqueue prompts
  run-uploads-no-reset            Same upload/enqueue chain without Redis FLUSHALL

Diagnostics:
  obsidian-cli-version            Print CLI surface version
  obsidian-cli-config             Print active launcher env values
  testing-help                    Show this help
HELP
}
