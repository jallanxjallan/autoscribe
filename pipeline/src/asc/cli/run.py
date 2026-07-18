"""User-facing run commands.

The run surface manages the three production runtime daemons:

    asc run loop    # start or confirm orchestrator + worker + scrivener daemons
    asc run stop    # stop all daemons, confirming if runtime work is present
    asc run status  # show daemons, active calls, and inbox contents/counts
    asc run reset   # stop daemons and clear runtime queues/state
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

from asc.redis.key import RedisKey
from asc.redis.primitives.keys import delete

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
    PID_FILE.write_text(
        json.dumps(pids, indent=2, sort_keys=True),
        encoding="utf-8",
    )


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

    # asc run owns the production daemon processes. Do not let the
    # orchestrator launch another worker and scrivener pair.
    env["ASC_ORCHESTRATOR_MANAGE_DOWNSTREAM"] = "0"

    return env


def _daemon_command(daemon: ManagedDaemon) -> list[str]:
    return [sys.executable, "-m", daemon.module]


def _reset_daemon_log() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_bytes(b"")


def _open_daemon_log():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    return LOG_FILE.open("ab", buffering=0)


def _start_daemon(
    daemon: ManagedDaemon,
    pids: dict[str, int],
) -> int:
    existing = pids.get(daemon.name)

    if existing is not None and _pid_alive(existing):
        typer.echo(f"{daemon.name}=running pid={existing}")
        return existing

    if existing is not None:
        typer.echo(f"{daemon.name}=replacing-stale pid={existing}")

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


def _stop_daemon(
    name: str,
    pid: int,
    *,
    force: bool = False,
) -> bool:
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

        if not _stop_daemon(
            daemon.name,
            pid,
            force=force,
        ):
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
    members = zsets.zrange(
        key,
        0,
        max(0, limit - 1),
    )

    calls: list[ActiveCallView] = []

    for member in members:
        text = str(member).strip()

        if not text:
            continue

        score = zsets.zscore(key, text)

        if score is None:
            continue

        calls.append(
            ActiveCallView(
                key=text,
                score=float(score),
            )
        )

    return calls


def _inboxes() -> tuple[InboxView, ...]:
    views: list[InboxView] = []

    for label, module_name in INBOX_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            views.append(
                InboxView(
                    name=label,
                    count=None,
                    items=(),
                )
            )
            continue

        views.append(
            InboxView(
                name=label,
                count=_module_count(module),
                items=_module_items(module),
            )
        )

    return tuple(views)


def _module_count(module) -> int | None:
    for attr_name in ("count", "length", "llen", "size"):
        attr = getattr(module, attr_name, None)

        if not callable(attr):
            continue

        try:
            return int(attr())
        except TypeError:
            continue

    return None


def _module_items(
    module,
    *,
    limit: int = 50,
) -> tuple[str, ...]:
    for attr_name in ("items", "list", "peek_all", "pending"):
        attr = getattr(module, attr_name, None)

        if not callable(attr):
            continue

        try:
            return tuple(
                str(item)
                for item in attr()[:limit]
            )
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

        if not callable(attr):
            continue

        try:
            return tuple(
                str(item)
                for item in attr(
                    queue_key,
                    0,
                    limit - 1,
                )
            )
        except Exception:
            pass

    return ()


def _module_queue_key(module) -> RedisKey | None:
    for name in dir(module):
        if name.endswith("INBOX_KEY") or name.endswith("QUEUE_KEY"):
            value = getattr(module, name)
            return (
                value
                if isinstance(value, RedisKey)
                else RedisKey(str(value))
            )

    return None


def _delete_redis_key(key: str | RedisKey) -> int:
    redis_key = (
        key
        if isinstance(key, RedisKey)
        else RedisKey(key)
    )

    return delete(redis_key)


def _clear_inbox(
    label: str,
    module_name: str,
) -> int | None:
    module = importlib.import_module(module_name)
    before = _module_count(module)

    for function_name in ("clear", "reset", "purge", "empty"):
        function = getattr(module, function_name, None)

        if callable(function):
            function()
            return before

    queue_key = _module_queue_key(module)

    if queue_key is None:
        raise RuntimeError(
            f"{label} inbox does not expose a queue key "
            "or clear function"
        )

    _delete_redis_key(queue_key)

    return before


def _clear_active_calls() -> int:
    active = importlib.import_module("asc.orchestrator.active")
    key = getattr(active, "ACTIVE_CALLS_KEY")
    count = len(_active_calls())

    _delete_redis_key(key)

    return count


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


def _is_idle_notice(line: str) -> bool:
    text = line.casefold()

    return (
        "daemon sleep" in text
        or "action='sleep'" in text
        or 'action="sleep"' in text
        or "operation=sleep" in text
        or "empty claim" in text
        or "empty claims" in text
        or "claim_wait" in text
        or "no_visible_calls" in text
    )


def _is_internal_noise(line: str) -> bool:
    text = line.casefold()

    return (
        "operation=poll_window" in text
        or "operation=handle call_key=" in text
        or "operation=defer_waiting" in text
        or "orchestratorrunreport(" in text
        or "scrivenerrunreport(" in text
        or "httpx http request:" in text
    )


def _is_error_line(line: str) -> bool:
    text = line.casefold()

    return (
        " traceback " in f" {text} "
        or " error " in f" {text} "
        or " critical " in f" {text} "
        or " exception" in text
        or text.startswith("traceback")
        or "daemon crash" in text
    )


def _log_time(line: str) -> str:
    if len(line) >= 19 and line[4] == "-" and line[7] == "-":
        return line[11:19]

    return ""


def _short_identity(line: str, prefix: str) -> str | None:
    marker = f"{prefix}:"
    start = line.find(marker)

    if start < 0:
        return None

    start += len(marker)
    end = start

    while end < len(line):
        char = line[end]

        if not char.isalnum():
            break

        end += 1

    identity = line[start:end]

    if not identity:
        return None

    return identity[-8:]


def _human_log_line(line: str) -> str | None:
    text = line.casefold()
    stamp = _log_time(line)
    prefix = f"{stamp}  " if stamp else ""

    if _is_error_line(line):
        return line.rstrip("\n")

    if _is_internal_noise(line):
        return None

    if _is_idle_notice(line):
        return f"{prefix}Runtime idle"

    if "daemon start name=" in text:
        if "name=orchestrator" in text:
            return f"{prefix}Orchestrator started"

        if "name=worker" in text:
            return f"{prefix}Worker started"

        if "name=scrivener" in text:
            return f"{prefix}Scrivener started"

    if "worker claimed_task_key=" in text:
        return f"{prefix}Worker started an LLM step"

    if (
        "worker claimed=true" in text
        and "action=execute_step" in text
    ):
        call_id = (
            _short_identity(line, "response")
            or _short_identity(line, "result")
            or _short_identity(line, "call")
        )

        ordinal = None

        for marker in ("response:", "result:"):
            start = line.find(marker)

            if start < 0:
                continue

            suffix_start = line.find(
                ":",
                start + len(marker),
            )

            if suffix_start >= 0:
                suffix_end = suffix_start + 1

                while (
                    suffix_end < len(line)
                    and line[suffix_end].isdigit()
                ):
                    suffix_end += 1

                ordinal = line[suffix_start + 1:suffix_end]

            break

        if call_id and ordinal:
            return (
                f"{prefix}LLM step {ordinal} completed "
                f"for call {call_id}"
            )

        if call_id:
            return f"{prefix}LLM step completed for call {call_id}"

        return f"{prefix}LLM step completed"

    if (
        "scrivener operation=executed" in text
        and "action=write_call" in text
    ):
        call_id = _short_identity(line, "call")

        if call_id:
            return f"{prefix}Call {call_id} accepted"

        return f"{prefix}Call accepted"

    if (
        "scrivener operation=executed" in text
        and "action=call_completed" in text
    ):
        call_id = (
            _short_identity(line, "response")
            or _short_identity(line, "result")
            or _short_identity(line, "call")
        )

        if call_id:
            return f"{prefix}Response saved for call {call_id}"

        return f"{prefix}Response saved"

    if "orchestrator operation=complete" in text:
        call_id = _short_identity(line, "call")

        if call_id:
            return f"{prefix}Call {call_id} completed"

        return f"{prefix}Call completed"

    return None


def _human_log_lines(lines: list[str]) -> list[str]:
    output: list[str] = []
    previous_raw: str | None = None
    idle_visible = False
    traceback_visible = False

    for line in lines:
        raw = line.rstrip("\n")

        if raw == previous_raw:
            continue

        previous_raw = raw

        if traceback_visible:
            if (
                raw.startswith(" ")
                or raw.startswith("\t")
                or raw.startswith("File ")
                or raw.startswith("Traceback")
                or raw.startswith("During handling")
                or (
                    raw
                    and not raw.startswith("202")
                    and not raw.startswith("worker ")
                )
            ):
                output.append(raw)
                continue

            traceback_visible = False

        human = _human_log_line(line)

        if human is None:
            continue

        if _is_error_line(line):
            traceback_visible = (
                "traceback" in line.casefold()
                or "daemon crash" in line.casefold()
            )
            idle_visible = False
            output.append(human)
            continue

        if human.endswith("Runtime idle"):
            if idle_visible:
                continue

            idle_visible = True
        else:
            idle_visible = False

        if output and output[-1] == human:
            continue

        output.append(human)

    return output


def _tail_raw_lines(
    path: Path,
    n: int,
) -> list[str]:
    if n <= 0 or not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as fh:
        lines = fh.readlines()

    return lines[-n:]


def _tail_human_lines(
    path: Path,
    n: int,
) -> list[str]:
    if n <= 0 or not path.exists():
        return []

    with path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as fh:
        lines = fh.readlines()

    return _human_log_lines(lines)[-n:]


def _follow_raw_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    with path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as fh:
        fh.seek(0, os.SEEK_END)

        while True:
            line = fh.readline()

            if line:
                typer.echo(line, nl=False)
                continue

            time.sleep(0.25)


def _follow_human_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)

    with path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as fh:
        fh.seek(0, os.SEEK_END)

        previous_raw: str | None = None
        idle_visible = False
        traceback_visible = False

        while True:
            line = fh.readline()

            if not line:
                time.sleep(0.25)
                continue

            raw = line.rstrip("\n")

            if raw == previous_raw:
                continue

            previous_raw = raw

            if traceback_visible:
                if (
                    raw.startswith(" ")
                    or raw.startswith("\t")
                    or raw.startswith("File ")
                    or raw.startswith("Traceback")
                    or raw.startswith("During handling")
                    or (
                        raw
                        and not raw.startswith("202")
                        and not raw.startswith("worker ")
                    )
                ):
                    typer.echo(raw)
                    continue

                traceback_visible = False

            human = _human_log_line(line)

            if human is None:
                continue

            if _is_error_line(line):
                traceback_visible = (
                    "traceback" in line.casefold()
                    or "daemon crash" in line.casefold()
                )
                idle_visible = False
                typer.echo(human)
                continue

            if human.endswith("Runtime idle"):
                if idle_visible:
                    continue

                idle_visible = True
            else:
                idle_visible = False

            typer.echo(human)


# ---------------------------------------------------------------------------
# commands


@app.command("loop")
def run_loop() -> None:
    """Refuse managed daemon startup; daemons are started manually."""

    typer.echo("Managed daemon startup is disabled.", err=True)
    typer.echo("Start daemons manually:", err=True)
    typer.echo("  python -m asc.orchestrator.daemon", err=True)
    typer.echo("  python -m asc.worker.daemon", err=True)
    typer.echo("  python -m asc.scrivener.daemon", err=True)
    raise typer.Exit(code=1)


@app.command("start", hidden=True)
def run_start_alias() -> None:
    """Deprecated alias; managed daemon startup remains disabled."""

    run_loop()


@app.command("stop")
def run_stop(
    force: bool = typer.Option(
        False,
        "--force",
        help="Use SIGKILL instead of SIGTERM.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Do not ask before stopping active runtime work.",
    ),
) -> None:
    """Stop all runtime daemons."""

    if not force and not yes and _runtime_has_work():
        run_status()

        if not typer.confirm(
            "Active calls or inbox items exist. Stop daemons anyway?"
        ):
            raise typer.Exit(code=1)

    _stop_recorded_daemons(force=force)


@app.command("reset")
def run_reset(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Do not ask before clearing runtime state.",
    ),
) -> None:
    """Stop daemons and clear runtime queues and active-call state."""

    if not yes and _runtime_has_work():
        run_status()

        if not typer.confirm(
            "Clear all runtime queues and active-call state?"
        ):
            raise typer.Exit(code=1)

    _stop_recorded_daemons()

    cleared_inboxes: list[str] = []

    for label, module_name in INBOX_MODULES:
        count = _clear_inbox(label, module_name)
        amount = "unknown" if count is None else str(count)
        cleared_inboxes.append(f"{label}={amount}")

    active_count = _clear_active_calls()

    _write_pids({})
    _reset_daemon_log()

    typer.echo("runtime reset")
    typer.echo(
        f"  inboxes cleared: {', '.join(cleared_inboxes)}"
    )
    typer.echo(f"  active calls cleared: {active_count}")
    typer.echo("  daemon records cleared")
    typer.echo("  log cleared")


@app.command("status")
def run_status() -> None:
    """Show daemon status, active calls, and inbox items."""

    pids = _read_pids()
    inboxes = _inboxes()

    typer.echo("daemons:")

    for daemon in DAEMONS:
        pid = pids.get(daemon.name)

        if pid is None:
            typer.echo(f"  {daemon.name}=not-running")
            continue

        if _pid_alive(pid):
            typer.echo(f"  {daemon.name}=running pid={pid}")
            continue

        matching_inbox = next(
            (
                inbox
                for inbox in inboxes
                if inbox.name == daemon.name
            ),
            None,
        )
        waiting = (
            matching_inbox.count
            if matching_inbox is not None
            else None
        )

        if waiting:
            typer.echo(
                f"  {daemon.name}=crashed pid={pid} "
                f"waiting={waiting}"
            )
        else:
            typer.echo(f"  {daemon.name}=stale pid={pid}")

    typer.echo("active_calls:")

    calls = _active_calls()

    if not calls:
        typer.echo("  none")

    for call in calls:
        visible = "visible" if call.visible else "sleeping"
        typer.echo(
            f"  {call.key} "
            f"score={call.score_label} "
            f"{visible}"
        )

    typer.echo("inboxes:")

    for inbox in inboxes:
        count = (
            "unavailable"
            if inbox.count is None
            else str(inbox.count)
        )

        typer.echo(f"  {inbox.name} count={count}")

        for item in inbox.items:
            typer.echo(f"    {item}")

    typer.echo(f"log={LOG_FILE}")


@app.command("log")
def run_log(
    lines: int = typer.Option(
        200,
        "--lines",
        "-n",
        help="Number of log lines to show.",
    ),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-f",
        help="Follow the daemon log.",
    ),
    raw: bool = typer.Option(
        False,
        "--raw",
        help="Show the unfiltered diagnostic log.",
    ),
) -> None:
    """Show the daemon activity log."""

    if not LOG_FILE.exists():
        typer.echo(f"log=missing path={LOG_FILE}")
        return

    if raw:
        for line in _tail_raw_lines(LOG_FILE, lines):
            typer.echo(line, nl=False)

        if follow:
            _follow_raw_log(LOG_FILE)

        return

    for line in _tail_human_lines(LOG_FILE, lines):
        typer.echo(line)

    if follow:
        _follow_human_log(LOG_FILE)


if __name__ == "__main__":
    app()