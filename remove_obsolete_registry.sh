#!/usr/bin/env bash
set -euo pipefail
root="${1:-.}"
rm -f "$root/asc/cli/registry.py"
rm -rf "$root/asc/registries"
printf 'Removed asc/cli/registry.py and asc/registries/\n'
