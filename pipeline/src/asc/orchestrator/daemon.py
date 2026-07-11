"""Orchestrator daemon entrypoint using the active-call zset.

``python -m asc.orchestrator.daemon`` runs the production orchestrator loop
until stopped by ``asc run stop``.
"""

from __future__ import annotations

from dataclasses import dataclass
import atexit
import importlib
import logging
import os
import subprocess
import sys
import time

from asc.orchestrator.active import (
    IDLE_SLEEP_SECONDS,
    active_call_window,
    bump_active_call,
    complete_active_call,
    defer_active_call,
    retry_active_call,
    seconds_until_next_visible,
)
from asc.orchestrator.handle import handle
from asc.redis.key import RedisKey
from asc.state.daemon import configure_logging


LOG = logging.getLogger(__name__)
DOWNSTREAM_INBOXES: tuple[str, ...] = ("asc.worker.inbox", "asc.scrivener.inbox")
DOWNSTREAM_DAEMONS: tuple[str, ...] = ("asc.worker.daemon", "asc.scrivener.daemon")
MANAGE_DOWNSTREAM = os.environ.get("ASC_ORCHESTRATOR_MANAGE_DOWNSTREAM", "1") != "0"


class _ManagedDownstream:
    def __init__(self, modules: tuple[str, ...]) -> None:
        self.modules = modules
        self.processes: dict[str, subprocess.Popen] = {}

    def start(self) -> None:
        if not MANAGE_DOWNSTREAM:
            return

        for module in self.modules:
            process = self.processes.get(module)
            if process is not None and process.poll() is None:
                continue

            LOG.info("orchestrator operation=downstream_start module=%s", module)
            self.processes[module] = subprocess.Popen(
                [sys.executable, "-m", module],
                start_new_session=True,
            )

    def stop(self) -> None:
        if not MANAGE_DOWNSTREAM:
            return

        for module, process in list(self.processes.items()):
            if process.poll() is not None:
                self.processes.pop(module, None)
                continue

            LOG.info("orchestrator operation=downstream_stop module=%s pid=%s", module, process.pid)
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                LOG.warning("orchestrator operation=downstream_kill module=%s pid=%s", module, process.pid)
                process.kill()
                process.wait(timeout=5)
            self.processes.pop(module, None)


DOWNSTREAM = _ManagedDownstream(DOWNSTREAM_DAEMONS)
atexit.register(DOWNSTREAM.stop)


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool
    call_key: str | None = None
    active: bool | None = None
    waiting: bool | None = None
    retry: bool | None = None
    action: str | None = None

    @property
    def post_key(self) -> str | None:
        return self.call_key

    @property
    def kind(self) -> str | None:
        if self.call_key is None:
            return None
        return RedisKey(self.call_key).kind


def _module_count(module) -> int | None:
    for attr_name in ("count", "length", "llen", "size"):
        attr = getattr(module, attr_name, None)
        if callable(attr):
            try:
                return int(attr())
            except TypeError:
                continue
    return None


def _module_queue_key(module):
    for name in dir(module):
        if name.endswith("INBOX_KEY") or name.endswith("QUEUE_KEY"):
            return getattr(module, name)
    return None


def _queue_count_from_key(queue_key) -> int | None:
    try:
        lists = importlib.import_module("asc.redis.primitives.lists")
    except ModuleNotFoundError:
        return None

    for attr_name in ("llen", "length", "count", "size"):
        attr = getattr(lists, attr_name, None)
        if callable(attr):
            try:
                return int(attr(queue_key))
            except Exception:
                pass
    return None


def _inbox_count(module_name: str) -> int | None:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None

    count = _module_count(module)
    if count is not None:
        return count

    queue_key = _module_queue_key(module)
    if queue_key is None:
        return None
    return _queue_count_from_key(queue_key)


def _downstream_sleeping() -> bool:
    """Return true when worker and scrivener have no queued work visible.

    The daemons sleep in Redis blocking claims. From the orchestrator's point of
    view, empty worker/scrivener inboxes mean downstream is asleep.
    """

    counts = [_inbox_count(module_name) for module_name in DOWNSTREAM_INBOXES]
    sleeping = all(count == 0 for count in counts if count is not None) and all(count is not None for count in counts)
    LOG.info("orchestrator operation=downstream_state counts=%s sleeping=%s", counts, sleeping)
    return sleeping


def _sleep_until_next(window) -> None:
    delay = seconds_until_next_visible(calls=window)
    sleep_seconds = delay if delay is not None else IDLE_SLEEP_SECONDS
    LOG.info("orchestrator operation=sleep no_visible_calls seconds=%.3f", sleep_seconds)
    time.sleep(sleep_seconds)


def run_cycle(
    *,
    wait: bool = True,
    target_keys: set[str] | None = None,
) -> OrchestratorRunReport:
    """Inspect and advance one active call."""

    now = time.time()
    window = active_call_window(target_keys=target_keys)
    LOG.info("orchestrator operation=poll_window size=%s", len(window))

    visible = [call for call in window if call.score <= now]
    if not visible:
        DOWNSTREAM.stop()
        if wait:
            _sleep_until_next(window)
        return OrchestratorRunReport(claimed=False, action="sleep")

    DOWNSTREAM.start()

    for call in visible:
        LOG.info("orchestrator operation=handle call_key=%s score=%s", call.key, call.score)
        result = handle(call.key)

        if not result.active:
            complete_active_call(call.key)
            LOG.info("orchestrator operation=complete call_key=%s", call.key)
            if not active_call_window(target_keys=target_keys):
                DOWNSTREAM.stop()
            return OrchestratorRunReport(
                claimed=True,
                call_key=call.key,
                active=False,
                waiting=False,
                retry=False,
                action="complete",
            )

        if result.retry:
            retry_active_call(call.key)
            LOG.info("orchestrator operation=retry_later call_key=%s", call.key)
            return OrchestratorRunReport(
                claimed=True,
                call_key=call.key,
                active=True,
                waiting=False,
                retry=True,
                action="retry_later",
            )

        if result.waiting:
            # A claimed worker/scrivener task has already left its inbox, so an
            # empty inbox does not prove the downstream daemon is idle. Bumping
            # immediately here creates a hot poll loop while the orchestrator is
            # waiting for the expected Redis artifact. Always defer briefly.
            defer_active_call(call.key)
            LOG.info("orchestrator operation=defer_waiting call_key=%s", call.key)
            return OrchestratorRunReport(
                claimed=True,
                call_key=call.key,
                active=True,
                waiting=True,
                action="defer_waiting",
            )

        bump_active_call(call.key)
        LOG.info("orchestrator operation=bump_active call_key=%s", call.key)
        return OrchestratorRunReport(
            claimed=True,
            call_key=call.key,
            active=True,
            waiting=False,
            retry=False,
            action="bump_active",
        )

    DOWNSTREAM.stop()
    if wait:
        _sleep_until_next(window)
    return OrchestratorRunReport(claimed=False, action="sleep")


def run_forever(*, target_keys: set[str] | None = None) -> None:
    """Run the orchestrator daemon forever."""

    configure_logging()
    LOG.info("orchestrator daemon start")
    try:
        while True:
            report = run_cycle(wait=True, target_keys=target_keys)
            LOG.info("orchestrator daemon report=%r", report)
    except KeyboardInterrupt:
        LOG.info("orchestrator daemon stop signal=KeyboardInterrupt")
        raise
    except Exception:
        LOG.exception("orchestrator daemon crash")
        raise


def main() -> None:
    """Run the production orchestrator loop."""

    run_forever()


if __name__ == "__main__":
    main()


__all__ = ["OrchestratorRunReport", "main", "run_cycle", "run_forever"]
