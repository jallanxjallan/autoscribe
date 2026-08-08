#!/usr/bin/env bash
set -euo pipefail

src_dir="$(cd "$(dirname "$0")" && pwd)"
target="${1:-$HOME/AutoScribe/feeder}"

[[ -d "$target/src/obs" ]] || { echo "Not a feeder checkout: $target" >&2; exit 1; }

for rel in src/obs/catalog.py src/obs/instruction_upload.py src/obs/ipc.py; do
  install -m 0644 "$src_dir/$rel" "$target/$rel"
done

python -m py_compile   "$target/src/obs/catalog.py"   "$target/src/obs/instruction_upload.py"   "$target/src/obs/ipc.py"

# Fail loudly if the live target does not contain the fixes this package promises.
grep -Fq 'cwd=Path.home()' "$target/src/obs/catalog.py"
grep -Fq '"instructions.sync": _instructions_sync' "$target/src/obs/ipc.py"
grep -Fq 'INSTRUCTION_PREFIXES = ("std.", "rol.", "cxt.", "tsk.")' "$target/src/obs/instruction_upload.py"
grep -Fq 'record["title"] = source.stem.strip()' "$target/src/obs/instruction_upload.py"

echo "Installed and verified Library/Feeder IPC fixes in $target"
echo "catalog.py: pipeline snapshot uses neutral cwd"
echo "ipc.py: instructions.sync registered"
echo "instruction_upload.py: cxt prefix + first-class filename title"
