#!/usr/bin/env bash
set -euo pipefail

src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app=/opt/autoscribe/app
cfg="$HOME/.config/autoscribe"
state="$HOME/.local/state/autoscribe"
run="$HOME/.local/run/autoscribe"
unitdir="$HOME/.config/systemd/user"
python=/opt/autoscribe/.venv/bin/python

fail(){ printf 'INSTALL FAILED: %s\n' "$*" >&2; exit 1; }

[[ -x "$python" ]] || fail "missing Python: $python"
[[ -w /opt/autoscribe ]] || fail "/opt/autoscribe is not writable by $(id -un)"

for f in \
    app/autoscribe/enqueue.py \
    app/autoscribe/exporter.py \
    app/autoscribe/executor.py \
    app/autoscribe/worker.py \
    app/daemon/executord.py \
    app/daemon/workerd.py \
    app/daemon/responsed.py \
    app/bin/asc; do
    [[ -f "$src/$f" ]] || fail "package missing $f"
done

printf 'Installing AutoScribe server snapshot 2026-09-30...\n'

systemctl --user stop autoscribe-responses.service 2>/dev/null || true
systemctl --user stop autoscribe-worker.service 2>/dev/null || true
systemctl --user stop autoscribe-executor.service 2>/dev/null || true
systemctl --user disable --now autoscribe-dispatch.service 2>/dev/null || true

mkdir -p "$app" "$cfg" "$state" "$run" "$unitdir" "$HOME/.local/bin" /opt/autoscribe/extensions
rm -rf "$app/autoscribe" "$app/daemon" "$app/tests" "$app/bin"
cp -a "$src/app/autoscribe" "$app/"
cp -a "$src/app/daemon" "$app/"
cp -a "$src/app/tests" "$app/"
cp -a "$src/app/bin" "$app/"
find "$app" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$app" -type f -name '*.pyc' -delete 2>/dev/null || true
chmod 755 "$app/daemon/"*.py "$app/daemon/"*.sh "$app/bin/asc"

install -m 755 "$src/extensions/prepend-seen.py" /opt/autoscribe/extensions/prepend-seen.py
install -m 644 "$src/extensions/registry.json" /opt/autoscribe/extensions/registry.json
ln -sfn "$app/bin/asc" "$HOME/.local/bin/asc"
install -m 600 "$src/autoscribe.env" "$cfg/autoscribe.env"

install -m 644 "$src/systemd/autoscribe-executor.service" "$unitdir/autoscribe-executor.service"
install -m 644 "$src/systemd/autoscribe-worker.service" "$unitdir/autoscribe-worker.service"
install -m 644 "$src/systemd/autoscribe-responses.service" "$unitdir/autoscribe-responses.service"

printf 'Compiling Python sources...\n'
"$python" -m compileall -q "$app/autoscribe" "$app/daemon" "$app/bin"

printf 'Running unit tests...\n'
PYTHONPATH="$app" "$python" -m unittest discover -s "$app/tests" -v

printf 'Checking Redis...\n'
redis-cli -h 127.0.0.1 -p 6379 PING | grep -qx PONG || fail "Redis unavailable"

printf 'Initializing ledger schema...\n'
AUTOSCRIBE_LEDGER_DB="$HOME/Data/ledger.sql" "$python" "$app/daemon/init-ledger.py" >/dev/null

systemctl --user daemon-reload
systemctl --user enable --now autoscribe-executor.service
systemctl --user enable --now autoscribe-worker.service
systemctl --user enable --now autoscribe-responses.service

printf '\nInstalled AutoScribe server snapshot 2026-09-30.\n'
printf 'Repo ingress: Rust srv-input from master. Repo output: Rust srv-writeback to autoscribe-output.\n'
printf 'Python responsed only coordinates pending responses and records successful Rust receipts.\n'
