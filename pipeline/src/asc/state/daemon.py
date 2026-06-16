# asc/state/daemon.py
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Protocol, TypeVar


log = logging.getLogger(__name__)

DEFAULT_CLAIM_TIMEOUT_SECONDS = int(os.environ.get("AUTOSCRIBE_DAEMON_CLAIM_TIMEOUT", "5"))
DEFAULT_IDLE_SECONDS = int(os.environ.get("AUTOSCRIBE_DAEMON_IDLE_SECONDS", "3600"))


class RunReport(Protocol):
    claimed: bool


ReportT = TypeVar("ReportT", bound=RunReport)
RunOnce = Callable[..., ReportT]


def idle_empty_limit(*, timeout: int | None = None, idle_seconds: int | None = None) -> int:
    """Return how many empty blocking-claim cycles make up the idle window."""

    actual_timeout = max(1, int(timeout or DEFAULT_CLAIM_TIMEOUT_SECONDS))
    actual_idle = max(1, int(idle_seconds or DEFAULT_IDLE_SECONDS))
    return max(1, actual_idle // actual_timeout)


def run_daemon(
    *,
    name: str,
    run_once: RunOnce[ReportT],
    timeout: int | None = None,
    empty_limit: int | None = None,
) -> None:
    """Run a package daemon using the shared lifecycle policy.

    Package runtimes still own their single-job semantics in ``run_once``.
    This function owns the daemon loop: it always uses the blocking claim path,
    never switches to non-blocking drain mode, and exits only after the configured
    idle window or an explicit process interruption/error.
    """

    actual_timeout = max(1, int(timeout or DEFAULT_CLAIM_TIMEOUT_SECONDS))
    actual_empty_limit = max(
        int(empty_limit or 0),
        idle_empty_limit(timeout=actual_timeout),
    )
    waited = actual_timeout * actual_empty_limit

    log.info(
        "%s daemon starting timeout=%s empty_limit=%s idle_seconds=%s",
        name,
        actual_timeout,
        actual_empty_limit,
        waited,
    )

    try:
        while True:
            report = run_once(timeout=actual_timeout, empty_limit=actual_empty_limit, wait=True)
            if not report.claimed:
                message = (
                    f"{name} queue idle after {actual_empty_limit} cycles "
                    f"({waited} seconds); daemon exiting cleanly"
                )
                log.info(message)
                print(message, flush=True)
                return
            log.info("%s claimed=True", name)
    except KeyboardInterrupt:
        log.info("%s daemon stopped by KeyboardInterrupt", name)
        raise
    except Exception:
        log.exception("%s daemon crashed", name)
        raise


__all__ = [
    "DEFAULT_CLAIM_TIMEOUT_SECONDS",
    "DEFAULT_IDLE_SECONDS",
    "RunReport",
    "idle_empty_limit",
    "run_daemon",
]
