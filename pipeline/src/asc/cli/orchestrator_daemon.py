"""Orchestrator daemon entrypoint using the active-call zset.

``python -m asc.orchestrator.daemon`` runs the production orchestrator loop
until stopped by ``asc run stop``.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import logging
import time

from asc.orchestrator.active import (
    IDLE_SLEEP_SECONDS,
    active_call_window,
    bump_active_call,
    complete_active_call,
    defer_active_call,
    seconds_until_next_visible,
)
from asc.orchestrator.handle import handle
from asc.redis.key import RedisKey
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging


LOG = logging.getLogger(__name__)
DOWNSTREAM_INBOXES: tuple[str, ...] = ("asc.worker.inbox", "asc.scrivener.inbox")


@dataclass(frozen=True, slots=True)
class OrchestratorRunReport:
    claimed: bool
    call_key: str | None = None
    active: bool | None = None
    waiting: bool | None = None
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


def run_once(*, timeout: int | None = None, empty_limit: int | None = None, wait: bool = True) -> OrchestratorRunReport:
    """Inspect and advance one active call."""

    del timeout, empty_limit

    now = time.time()
    window = active_call_window()
    LOG.info("orchestrator operation=poll_window size=%s", len(window))

    visible = [call for call in window if call.score <= now]
    if not visible:
        if wait:
            _sleep_until_next(window)
        return OrchestratorRunReport(claimed=False, action="sleep")

    for call in visible:
        LOG.info("orchestrator operation=handle call_key=%s score=%s", call.key, call.score)
        result = handle(call.key)

        if not result.active:
            complete_active_call(call.key)
            LOG.info("orchestrator operation=complete call_key=%s", call.key)
            return OrchestratorRunReport(
                claimed=True,
                call_key=call.key,
                active=False,
                waiting=False,
                action="complete",
            )

        if result.waiting:
            if _downstream_sleeping():
                bump_active_call(call.key)
                LOG.info("orchestrator operation=bump_waiting call_key=%s", call.key)
                return OrchestratorRunReport(
                    claimed=True,
                    call_key=call.key,
                    active=True,
                    waiting=True,
                    action="bump_waiting",
                )

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
            action="bump_active",
        )

    if wait:
        _sleep_until_next(window)
    return OrchestratorRunReport(claimed=False, action="sleep")


def run_forever(*, timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS, empty_limit: int | None = None) -> None:
    """Run the orchestrator daemon forever."""

    configure_logging()
    LOG.info("orchestrator daemon start timeout=%s empty_limit=%s", timeout, empty_limit)
    try:
        while True:
            report = run_once(timeout=timeout, empty_limit=empty_limit, wait=True)
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


__all__ = ["OrchestratorRunReport", "main", "run_forever", "run_once"]
