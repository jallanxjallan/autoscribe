#!/usr/bin/env bash
set -euo pipefail

src_dir="$(cd "$(dirname "$0")" && pwd)/feeder"
target="${1:-$HOME/AutoScribe/feeder}"

[[ -d "$target/src/obs" ]] || { echo "Not a feeder checkout: $target" >&2; exit 1; }

cp "$src_dir/README.md" "$target/README.md"
cp "$src_dir/src/obs/cli.py" "$target/src/obs/cli.py"
cp "$src_dir/src/obs/retrieval.py" "$target/src/obs/retrieval.py"
cp "$src_dir/tests/test_retrieve_results.py" "$target/tests/test_retrieve_results.py"
rm -f "$target/src/obs/downloads.py"

echo "Installed durable Retrieve Results fix into $target"
