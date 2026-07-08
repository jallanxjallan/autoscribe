"""User-facing run commands.

The run surface manages the three production runtime daemons:

    asc run loop    # start or confirm orchestrator + worker + scrivener daemons
    asc run stop    # stop all daemons, confirming if runtime work is present
    asc run status  # show daemons, active calls, and inbox contents/counts
    asc run log     # show the shared daemon operation log

The orchestrator owns active-call progression. The worker owns engine execution.
The scrivener owns ledger writes. Daemons run until stopped with ``asc run stop``.
"""

from __future__ import annotations

import importlib
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import typer

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Run and inspect AutoScribe runtime daemons.",
)

RUN_DIR = Path(os.environ.get("AUTOSCRIBE_RUN_DIR", "/tmp/autoscribe"))
PID_FILE = RUN_DIR / "runtime-daemons.json"
LOG_DIR = Path(os.environ.get("AUTOSCRIBE_LOG_DIR", str(RUN_DIR / "logs")))
LOG_FILE = Path(os.environ.get("AUTOSCRIBE_DAEMON_LOG", str(LOG_DIR / "runtime.log")))


@dataclass(frozen=True, slots=True)
class ManagedDaemon:
    name: str
    module: str


DAEMONS: tuple[ManagedDaemon, ...] = (
    ManagedDaemon(name="orchestrator", module="asc.orchestrator.daemon"),
    ManagedDaemon(name="worker", module="asc.worker.daemon"),
    ManagedDaemon(name="scrivener", module="asc.scrivener.daemon"),
)

INBOX_MODULES: tuple[tuple[str, str], ...] = (
    ("orchestrator", "asc.orchestrator.inbox"),
    ("worker", "asc.worker.inbox"),
    ("scrivener", "asc.scrivener.inbox"),
)


@dataclass(frozen=True, slots=True)
class ActiveCallView:
    key: str
    score: float

    @property
    def visible(self) -> bool:
        return self.score <= time.time()

    @property
    def score_label(self) -> str:
        if self.score == 0:
            return "0"
        return f"{self.score:.3f}"


@dataclass(frozen=True, slots=True)
class InboxView:
    name: str
    count: int | None
    items: tuple[str, ...]


# ---------------------------------------------------------------------------
# pid/process helpers


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
    RUN_DIR.mkdir(parents=True, exist_ok=True)
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


def _daemon_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["AUTOSCRIBE_DAEMON_LOG"] = str(LOG_FILE)
    return env


def _daemon_command(daemon: ManagedDaemon) -> list[str]:
    return [sys.executable, "-m", daemon.module]


def _open_daemon_log():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_FILE.open("ab", buffering=0)


def _start_daemon(daemon: ManagedDaemon, pids: dict[str, int]) -> int:
    existing = pids.get(daemon.name)
    if existing is not None and _pid_alive(existing):
        typer.echo(f"{daemon.name}=running pid={existing}")
        return existing

    log_handle = _open_daemon_log()
    try:
        process = subprocess.Popen(
            _daemon_command(daemon),
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=_daemon_env(),
        )
    finally:
        log_handle.close()

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


def _stop_recorded_daemons(*, force: bool = False) -> None:
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


# ---------------------------------------------------------------------------
# runtime inspection helpers


def _active_calls(*, limit: int = 1000) -> list[ActiveCallView]:
    try:
        active = importlib.import_module("asc.orchestrator.active")
        zsets = importlib.import_module("asc.redis.primitives.zsets")
    except ModuleNotFoundError:
        return []

    key = getattr(active, "ACTIVE_CALLS_KEY")
    members = zsets.zrange(key, 0, max(0, limit - 1))
    calls: list[ActiveCallView] = []
    for member in members:
        text = str(member).strip()
        if not text:
            continue
        score = zsets.zscore(key, text)
        if score is None:
            continue
        calls.append(ActiveCallView(key=text, score=float(score)))
    return calls


def _inboxes() -> tuple[InboxView, ...]:
    views: list[InboxView] = []
    for label, module_name in INBOX_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            views.append(InboxView(name=label, count=None, items=()))
            continue
        views.append(InboxView(name=label, count=_module_count(module), items=_module_items(module)))
    return tuple(views)


def _module_count(module) -> int | None:
    for attr_name in ("count", "length", "llen", "size"):
        attr = getattr(module, attr_name, None)
        if callable(attr):
            try:
                return int(attr())
            except TypeError:
                continue
    return None


def _module_items(module, *, limit: int = 50) -> tuple[str, ...]:
    for attr_name in ("items", "list", "peek_all", "pending"):
        attr = getattr(module, attr_name, None)
        if callable(attr):
            try:
                return tuple(str(item) for item in attr()[:limit])
            except Exception:
                pass

    queue_key = _module_queue_key(module)
    if queue_key is None:
        return ()

    try:
        lists = importlib.import_module("asc.redis.primitives.lists")
    except ModuleNotFoundError:
        return ()

    for attr_name in ("lrange", "range", "list_range"):
        attr = getattr(lists, attr_name, None)
        if callable(attr):
            try:
                return tuple(str(item) for item in attr(queue_key, 0, limit - 1))
            except Exception:
                pass
    return ()


def _module_queue_key(module):
    for name in dir(module):
        if name.endswith("INBOX_KEY") or name.endswith("QUEUE_KEY"):
            return getattr(module, name)
    return None


def _runtime_inbox_count() -> int:
    total = 0
    for inbox in _inboxes():
        total += inbox.count or 0
    return total


def _runtime_has_work() -> bool:
    if _active_calls():
        return True
    return _runtime_inbox_count() > 0


# ---------------------------------------------------------------------------
# log helpers


def _tail_lines(path: Path, n: int) -> list[str]:
    if n <= 0:
        return []
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    return lines[-n:]


def _follow_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(0, os.SEEK_END)
        while True:
            line = fh.readline()
            if line:
                typer.echo(line, nl=False)
                continue
            time.sleep(0.25)


# ---------------------------------------------------------------------------
# commands


@app.command("loop")
def run_loop() -> None:
    """Start or confirm all runtime daemons and keep them running."""

    pids = _read_pids()
    for daemon in DAEMONS:
        _start_daemon(daemon, pids)
    _write_pids(pids)
    typer.echo(f"log={LOG_FILE}")


@app.command("start", hidden=True)
def run_start_alias() -> None:
    """Deprecated alias for `asc run loop`."""

    run_loop()


@app.command("stop")
def run_stop(
    force: bool = typer.Option(False, "--force", help="Use SIGKILL instead of SIGTERM."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before stopping active runtime work."),
) -> None:
    """Stop all runtime daemons."""

    if not force and not yes and _runtime_has_work():
        run_status()
        if not typer.confirm("Active calls or inbox items exist. Stop daemons anyway?"):
            raise typer.Exit(code=1)

    _stop_recorded_daemons(force=force)


@app.command("status")
def run_status() -> None:
    """Show daemon status, active calls, and inbox items."""

    pids = _read_pids()
    typer.echo("daemons:")
    for daemon in DAEMONS:
        pid = pids.get(daemon.name)
        if pid is None:
            typer.echo(f"  {daemon.name}=not-running")
        elif _pid_alive(pid):
            typer.echo(f"  {daemon.name}=running pid={pid}")
        else:
            typer.echo(f"  {daemon.name}=stale pid={pid}")

    typer.echo("active_calls:")
    calls = _active_calls()
    if not calls:
        typer.echo("  none")
    for call in calls:
        visible = "visible" if call.visible else "sleeping"
        typer.echo(f"  {call.key} score={call.score_label} {visible}")

    typer.echo("inboxes:")
    for inbox in _inboxes():
        count = "unavailable" if inbox.count is None else str(inbox.count)
        typer.echo(f"  {inbox.name} count={count}")
        for item in inbox.items:
            typer.echo(f"    {item}")

    typer.echo(f"log={LOG_FILE}")


@app.command("log")
def run_log(
    lines: int = typer.Option(200, "--lines", "-n", help="Number of log lines to show."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow the daemon log."),
) -> None:
    """Show the shared daemon operation log."""

    if not LOG_FILE.exists():
        typer.echo(f"log=missing path={LOG_FILE}")
        return

    for line in _tail_lines(LOG_FILE, lines):
        typer.echo(line, nl=False)

    if follow:
        _follow_log(LOG_FILE)


if __name__ == "__main__":
    app()
