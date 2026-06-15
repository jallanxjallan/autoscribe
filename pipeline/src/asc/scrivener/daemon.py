from __future__ import annotations

import logging

from asc.scrivener.runtime import ScrivenerRunReport, run_forever, run_once

log = logging.getLogger(__name__)


def main() -> None:
    """Single-pass module entry point for manual daemon testing.

    The real process lifecycle still belongs to ``asc.cli.run``.  This module
    only exposes a direct ``python -m asc.scrivener.daemon`` smoke-test surface,
    matching the other daemon modules.
    """

    logging.basicConfig(level=logging.INFO)
    report = run_once(timeout=0)
    log.info("scrivener claimed=%s", report.claimed)
    if report.claimed:
        log.info("scrivener job=%s cursor=%s", report.job_key, report.cursor_key)


if __name__ == "__main__":
    main()


__all__ = ["ScrivenerRunReport", "main", "run_forever", "run_once"]
