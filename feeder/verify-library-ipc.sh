#!/usr/bin/env bash
set -euo pipefail
vault="${1:-$PWD}"
obs_bin="${AUTOSCRIBE_OBS_BIN:-${OBS_BIN:-$HOME/Python3.13Env/bin/obs}}"

echo "obs: $obs_bin"
"$obs_bin" --vault "$vault" state >/dev/null
echo '{"operation":"pipeline.snapshot","kind":"control"}' | "$obs_bin" --vault "$vault" ipc
