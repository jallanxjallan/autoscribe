"""User-facing run commands.

The run surface manages the two long-lived runtime services:

    asc run start   # start or confirm orchestrator + worker daemons
    asc run stop    # stop both daemons
    asc run status  # show daemon and queue status

Internal queue phases are deliberately not exposed here.  The orchestrator owns
runtime cursor progression and ledger writes.  The worker owns worker custody
and engine execution.
"""

from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Start, stop, and inspect AutoScribe runtime daemons.",
)

PID_DIR = Path(os.environ.get("AUTOSCRIBE_RUN_DIR", "/tmp/autoscribe"))
PID_FILE = PID_DIR / "runtime-daemons.json"


@dataclass(frozen=True, slots=True)
class ManagedDaemon:
    name: str
    module: str


DAEMONS: tuple[ManagedDaemon, ...] = (
    ManagedDaemon(name="orchestrator", module="asc.orchestrator.daemon"),
    ManagedDaemon(name="worker", module="asc.workers.daemon"),
)


def _read_pids() -> dict[str, int]:
    if not PID_FILE.exists():
        return {}
    try:
        raw = json.loads(PID_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for name, pid in raw.items():
        try:
            out[str(name)] = int(pid)
        except (TypeError, ValueError):
            continue
    return out


def _write_pids(pids: dict[str, int]) -> None:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps(pids, indent=2, sort_keys=True), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _start_daemon(daemon: ManagedDaemon, pids: dict[str, int]) -> int:
    existing = pids.get(daemon.name)
    if existing is not None and _pid_alive(existing):
        typer.echo(f"{daemon.name}=running pid={existing}")
        return existing

    process = subprocess.Popen(
        [sys.executable, "-m", daemon.module],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pids[daemon.name] = int(process.pid)
    typer.echo(f"{daemon.name}=started pid={process.pid}")
    return int(process.pid)


def _stop_daemon(name: str, pid: int, *, force: bool = False) -> bool:
    if not _pid_alive(pid):
        typer.echo(f"{name}=stale pid={pid}")
        return True

    sig = signal.SIGKILL if force else signal.SIGTERM
    os.kill(pid, sig)
    typer.echo(f"{name}=stopped pid={pid}")
    return True


@app.command("start")
def run_start() -> None:
    """Start or confirm both runtime daemons."""

    pids = _read_pids()
    for daemon in DAEMONS:
        _start_daemon(daemon, pids)
    _write_pids(pids)


@app.command("stop")
def run_stop(
    force: bool = typer.Option(False, "--force", help="Use SIGKILL instead of SIGTERM."),
) -> None:
    """Stop both runtime daemons."""

    pids = _read_pids()
    remaining: dict[str, int] = {}
    for daemon in DAEMONS:
        pid = pids.get(daemon.name)
        if pid is None:
            typer.echo(f"{daemon.name}=not-recorded")
            continue
        if not _stop_daemon(daemon.name, pid, force=force):
            remaining[daemon.name] = pid
    _write_pids(remaining)


@app.command("status")
def run_status() -> None:
    """Show daemon status and lightweight queue counts."""

    pids = _read_pids()
    for daemon in DAEMONS:
        pid = pids.get(daemon.name)
        if pid is None:
            typer.echo(f"{daemon.name}=not-running")
        elif _pid_alive(pid):
            typer.echo(f"{daemon.name}=running pid={pid}")
        else:
            typer.echo(f"{daemon.name}=stale pid={pid}")

    for label, module_name in {
        "orchestrator_pending": "asc.state.orchestrator_queue",
        "worker_pending": "asc.state.worker_queue",
        "worker_outcome": "asc.state.worker_outcome_queue",
        "runtime_active": "asc.state.runtime_active",
    }.items():
        typer.echo(f"{label}={_queue_count(module_name)}")


def _queue_count(module_name: str) -> str:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return "unavailable"

    for attr_name in ("count", "length", "llen", "size"):
        attr = getattr(module, attr_name, None)
        if callable(attr):
            try:
                return str(attr())
            except TypeError:
                continue
    return "unknown"


if __name__ == "__main__":
    app()
