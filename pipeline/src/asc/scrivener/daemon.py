"""Scrivener daemon entrypoint.

``python -m asc.scrivener.daemon`` runs the production scrivener loop until
stopped by ``asc run stop``.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from asc.scrivener import inbox as scrivener_inbox
from asc.scrivener.execute import ScrivenerExecutor
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon


LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScrivenerRunReport:
    claimed: bool
    task_key: str | None = None
    action: str | None = None
    table: str | None = None
    data_key: str | None = None


def run_once(
    *,
    timeout: int | None = None,
    empty_limit: int | None = None,
    wait: bool = True,
) -> ScrivenerRunReport:
    """Claim and execute one scrivener task."""

    claimed = scrivener_inbox.daemon_claim(timeout=timeout or 0, empty_limit=None) if wait else scrivener_inbox.claim()

    if claimed is None:
        return ScrivenerRunReport(claimed=False)

    task_key = str(claimed).strip()
    if not task_key:
        raise ValueError("scrivener claimed an empty task key")

    LOG.info("scrivener operation=claimed task_key=%s", task_key)

    result = ScrivenerExecutor().execute(task_key)

    report = ScrivenerRunReport(
        claimed=True,
        task_key=result.task_key,
        action=result.action,
        table=result.table,
        data_key=result.data_key,
    )
    LOG.info(
        "scrivener operation=executed task_key=%s action=%s table=%s data_key=%s",
        report.task_key,
        report.action,
        report.table,
        report.data_key,
    )
    return report


def run_forever(*, timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS, empty_limit: int | None = None) -> None:
    """Run the scrivener daemon loop until process termination."""

    configure_logging()
    run_daemon(name="scrivener", run_once=run_once, timeout=timeout, empty_limit=empty_limit)


def main() -> None:
    """Run the production scrivener loop."""

    run_forever()


if __name__ == "__main__":
    main()


__all__ = ["ScrivenerRunReport", "main", "run_forever", "run_once"]
