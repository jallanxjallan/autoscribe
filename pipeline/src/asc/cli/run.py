"""User-facing run commands.

The run surface manages the three runtime services:

    asc run single  # process one score-0 call, then stop daemons
    asc run drain   # process all current score-0 calls, then stop daemons
    asc run loop    # start or confirm orchestrator + worker + scrivener daemons
    asc run stop    # stop all daemons, confirming if runtime work is present
    asc run status  # show daemons, active calls, and inbox contents/counts

The orchestrator owns active-call progression. The worker owns engine execution.
The scrivener owns ledger writes. `single` and `drain` snapshot score-0 calls
at launch and keep the daemons alive until those calls are no longer active and
runtime inboxes have drained.
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
from typing import Iterable

import typer

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Run and inspect AutoScribe runtime daemons.",
)

PID_DIR = Path(os.environ.get("AUTOSCRIBE_RUN_DIR", "/tmp/autoscribe"))
PID_FILE = PID_DIR / "runtime-daemons.json"
QUIET_DRAIN_TICKS = 3
MONITOR_SLEEP_SECONDS = 0.25


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


def _daemon_env(*, target_keys: tuple[str, ...] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if target_keys is not None:
        env["AUTOSCRIBE_TARGET_CALLS"] = json.dumps(list(target_keys))
    return env


def _daemon_command(daemon: ManagedDaemon, *, target_keys: tuple[str, ...] | None = None) -> list[str]:
    if daemon.name == "orchestrator" and target_keys is not None:
        return [
            sys.executable,
            "-c",
            (
                "import json, os; "
                "from asc.orchestrator.daemon import run_forever; "
                "run_forever(target_keys=set(json.loads(os.environ['AUTOSCRIBE_TARGET_CALLS'])))"
            ),
        ]

    return [
        sys.executable,
        "-c",
        f"from {daemon.module} import run_forever; run_forever()",
    ]


def _start_daemon(
    daemon: ManagedDaemon,
    pids: dict[str, int],
    *,
    target_keys: tuple[str, ...] | None = None,
) -> int:
    existing = pids.get(daemon.name)
    if existing is not None and _pid_alive(existing):
        typer.echo(f"{daemon.name}=running pid={existing}")
        return existing

    process = subprocess.Popen(
        _daemon_command(daemon, target_keys=target_keys),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=_daemon_env(target_keys=target_keys),
    )
    pids[daemon.name] = int(process.pid)
    typer.echo(f"{daemon.name}=started pid={process.pid}")
    return int(process.pid)


def _start_debug_daemon(daemon: ManagedDaemon, pids: dict[str, int]) -> subprocess.Popen[bytes]:
    existing = pids.get(daemon.name)
    if existing is not None and _pid_alive(existing):
        raise RuntimeError(f"{daemon.name} already running pid={existing}; run `asc run stop` first")

    process = subprocess.Popen(
        _daemon_command(daemon),
        stdin=subprocess.DEVNULL,
        stdout=None,
        stderr=None,
        start_new_session=False,
        env=_daemon_env(),
    )
    pids[daemon.name] = int(process.pid)
    typer.echo(f"{daemon.name}=debug pid={process.pid}")
    return process


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


def _stop_processes(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    for name, process in processes.items():
        if process.poll() is None:
            process.terminate()
            typer.echo(f"{name}=terminating pid={process.pid}")

    deadline = time.monotonic() + 5
    for name, process in processes.items():
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if process.poll() is None:
            process.kill()
            typer.echo(f"{name}=killed pid={process.pid}")


def _remove_managed_pids(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    saved = _read_pids()
    for name, process in processes.items():
        if saved.get(name) == process.pid:
            saved.pop(name)
    _write_pids(saved)


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


def _score_zero_calls() -> tuple[str, ...]:
    return tuple(call.key for call in _active_calls() if call.score == 0)


def _active_key_set() -> set[str]:
    return {call.key for call in _active_calls()}


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
# controlled run modes


def _start_all(*, target_keys: tuple[str, ...] | None = None) -> dict[str, subprocess.Popen[bytes]]:
    pids = _read_pids()
    already = {daemon.name: pid for daemon in DAEMONS if (pid := pids.get(daemon.name)) and _pid_alive(pid)}
    if already:
        names = ", ".join(f"{name}={pid}" for name, pid in sorted(already.items()))
        raise RuntimeError(f"runtime already running: {names}; run `asc run stop` first")

    processes: dict[str, subprocess.Popen[bytes]] = {}
    for daemon in DAEMONS:
        process = subprocess.Popen(
            _daemon_command(daemon, target_keys=target_keys),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=_daemon_env(target_keys=target_keys),
        )
        processes[daemon.name] = process
        pids[daemon.name] = int(process.pid)
        typer.echo(f"{daemon.name}=started pid={process.pid}")
    _write_pids(pids)
    return processes


def _raise_if_child_exited(processes: dict[str, subprocess.Popen[bytes]]) -> None:
    exited = [name for name, process in processes.items() if process.poll() is not None]
    if not exited:
        return
    details = ", ".join(
        f"{name}={processes[name].returncode}" for name in exited
    )
    raise RuntimeError(f"daemon exited before run completed: {details}")


def _run_until_complete(target_keys: tuple[str, ...], processes: dict[str, subprocess.Popen[bytes]]) -> None:
    targets = set(target_keys)
    quiet_ticks = 0

    while True:
        active = _active_calls()
        target_visible = any(call.key in targets and call.visible for call in active)
        inbox_count = _runtime_inbox_count()

        if not target_visible and inbox_count == 0:
            quiet_ticks += 1
            if quiet_ticks >= QUIET_DRAIN_TICKS:
                return
        else:
            quiet_ticks = 0
            _raise_if_child_exited(processes)

        time.sleep(MONITOR_SLEEP_SECONDS)


def _controlled_run(target_keys: tuple[str, ...], *, label: str) -> None:
    if not target_keys:
        typer.echo(f"{label}=no-score-0-calls")
        return

    typer.echo(f"{label}=starting calls={len(target_keys)}")
    processes: dict[str, subprocess.Popen[bytes]] = {}
    try:
        processes = _start_all(target_keys=target_keys)
        _run_until_complete(target_keys, processes)
        typer.echo(f"{label}=complete")
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        _stop_processes(processes)
        _remove_managed_pids(processes)


@app.command("single")
def run_single() -> None:
    """Process one score-0 call, then stop all daemons."""

    calls = _score_zero_calls()
    _controlled_run(calls[:1], label="single")


@app.command("drain")
def run_drain() -> None:
    """Process all currently score-0 calls, then stop all daemons."""

    _controlled_run(_score_zero_calls(), label="drain")


@app.command("loop")
def run_loop(
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Run daemons in the foreground with stdout/stderr attached to this terminal.",
    ),
) -> None:
    """Start or confirm all runtime daemons and keep them running."""

    pids = _read_pids()

    if not debug:
        for daemon in DAEMONS:
            _start_daemon(daemon, pids)
        _write_pids(pids)
        return

    processes: dict[str, subprocess.Popen[bytes]] = {}
    try:
        for daemon in DAEMONS:
            processes[daemon.name] = _start_debug_daemon(daemon, pids)
        _write_pids(pids)
        typer.echo("debug=attached; press Ctrl-C to stop daemons")

        while True:
            _raise_if_child_exited(processes)
            time.sleep(0.25)
    except KeyboardInterrupt:
        typer.echo("debug=stopping")
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        _stop_processes(processes)
        _remove_managed_pids(processes)


@app.command("start", hidden=True)
def run_start_alias(
    debug: bool = typer.Option(False, "--debug"),
) -> None:
    """Deprecated alias for `asc run loop`."""

    run_loop(debug=debug)


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


if __name__ == "__main__":
    app()
