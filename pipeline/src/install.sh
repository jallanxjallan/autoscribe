#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-.}"
if [[ ! -d "$TARGET/asc" ]]; then
  echo "ERROR: target must be the package root containing asc/: $TARGET" >&2
  exit 1
fi

cp -a asc/. "$TARGET/asc/"
rm -f "$TARGET/asc/state/publications.py"
find "$TARGET/asc/state" -maxdepth 1 -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
python -m compileall -q "$TARGET/asc"
echo "Installed hash-addressed plan/instruction versioning; publication domain removed."
