"""Orchestrator daemon entrypoint using the active-call zset.

``python -m asc.orchestrator.daemon`` runs the production orchestrator loop
until stopped by ``asc run stop``.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
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
            # Defer briefly while waiting for the expected Redis artifact to
            # avoid a hot poll loop.
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
