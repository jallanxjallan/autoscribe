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

DEFAULT_CLAIM_TIMEOUT_SECONDS = 0
DEFAULT_LOG_PATH = Path("/tmp/autoscribe/logs/runtime.log")


class RunReport(Protocol):
    claimed: bool


ReportT = TypeVar("ReportT", bound=RunReport)
RunCycle = Callable[..., ReportT]


def configure_logging() -> None:
    """Shared logging setup for all package daemons."""

    level = "INFO"
    log_path = DEFAULT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    if not any(
        isinstance(handler, WatchedFileHandler)
        and Path(handler.baseFilename) == log_path
        for handler in root.handlers
    ):
        file_handler = WatchedFileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if not any(getattr(handler, "_autoscribe_stderr", False) for handler in root.handlers):
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(formatter)
        stderr_handler._autoscribe_stderr = True
        root.addHandler(stderr_handler)


def run_daemon(
    *,
    name: str,
    run_cycle: RunCycle[ReportT],
    timeout: int | None = None,
) -> None:
    """Run a blocking-queue daemon until the process is stopped."""

    actual_timeout = 0 if timeout is None else max(0, int(timeout))
    log.info("daemon start name=%s timeout=%s", name, actual_timeout)

    try:
        while True:
            log.info("daemon sleep name=%s operation=claim_wait", name)
            report = run_cycle(timeout=actual_timeout)
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
    "RunReport",
    "configure_logging",
    "run_daemon",
]
