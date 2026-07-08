# asc/state/daemon.py

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from logging.handlers import WatchedFileHandler
from pathlib import Path
from typing import Protocol, TypeVar


log = logging.getLogger(__name__)

DEFAULT_CLAIM_TIMEOUT_SECONDS = int(os.environ.get("AUTOSCRIBE_DAEMON_CLAIM_TIMEOUT", "0"))
DEFAULT_IDLE_SECONDS = int(os.environ.get("AUTOSCRIBE_DAEMON_IDLE_SECONDS", "3600"))
DEFAULT_LOG_PATH = Path(os.environ.get("AUTOSCRIBE_DAEMON_LOG", "/tmp/autoscribe/logs/runtime.log"))


class RunReport(Protocol):
    claimed: bool


ReportT = TypeVar("ReportT", bound=RunReport)
RunOnce = Callable[..., ReportT]


def configure_logging() -> None:
    """Shared logging setup for all package daemons."""

    level = os.environ.get("AUTOSCRIBE_LOG_LEVEL", "INFO").upper()
    log_path = Path(os.environ.get("AUTOSCRIBE_DAEMON_LOG", str(DEFAULT_LOG_PATH)))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    if not any(isinstance(handler, WatchedFileHandler) and Path(handler.baseFilename) == log_path for handler in root.handlers):
        file_handler = WatchedFileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if not any(getattr(handler, "_autoscribe_stderr", False) for handler in root.handlers):
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(formatter)
        stderr_handler._autoscribe_stderr = True
        root.addHandler(stderr_handler)


def idle_empty_limit(*, timeout: int | None = None, idle_seconds: int | None = None) -> int:
    """Return how many empty blocking-claim cycles make up the idle window.

    Kept for compatibility with imports. Production daemons no longer use this
    to exit when idle; they block in Redis until ``asc run stop`` terminates
    the process.
    """

    actual_timeout = max(1, int(timeout or DEFAULT_CLAIM_TIMEOUT_SECONDS or 1))
    actual_idle = max(1, int(idle_seconds or DEFAULT_IDLE_SECONDS))
    return max(1, actual_idle // actual_timeout)


def run_daemon(
    *,
    name: str,
    run_once: RunOnce[ReportT],
    timeout: int | None = None,
    empty_limit: int | None = None,
) -> None:
    """Run a package daemon until the process is stopped.

    Worker and scrivener sleep inside the Redis blocking claim path. There is no
    idle shutdown and no test/drain mode in the daemon lifecycle anymore.
    """

    actual_timeout = 0 if timeout is None else max(0, int(timeout))

    log.info("daemon start name=%s timeout=%s empty_limit=%s", name, actual_timeout, empty_limit)

    try:
        while True:
            log.info("daemon sleep name=%s operation=claim_wait", name)
            report = run_once(timeout=actual_timeout, empty_limit=None, wait=True)
            if not report.claimed:
                log.info("daemon wake name=%s operation=claim_empty", name)
                continue
            log.info("daemon operation name=%s claimed=True report=%r", name, report)
    except KeyboardInterrupt:
        log.info("daemon stop name=%s signal=KeyboardInterrupt", name)
        raise
    except Exception:
        log.exception("daemon crash name=%s", name)
        raise


__all__ = [
    "DEFAULT_CLAIM_TIMEOUT_SECONDS",
    "DEFAULT_IDLE_SECONDS",
    "RunReport",
    "configure_logging",
    "idle_empty_limit",
    "run_daemon",
]
