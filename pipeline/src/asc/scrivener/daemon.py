"""Scrivener daemon entrypoint."""

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


def process_next(*, timeout: int = 0) -> ScrivenerRunReport:
    """Claim and execute the next scrivener task."""

    claimed = scrivener_inbox.daemon_claim(timeout=timeout, empty_limit=None)
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


def run_forever(*, timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS) -> None:
    """Run the scrivener daemon until process termination."""

    configure_logging()
    run_daemon(name="scrivener", run_cycle=process_next, timeout=timeout)


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()


__all__ = ["ScrivenerRunReport", "main", "process_next", "run_forever"]
