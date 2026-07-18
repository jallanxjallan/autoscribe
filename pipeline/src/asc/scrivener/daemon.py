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
    artifact_key: str | None = None
    kind: str | None = None
    table: str | None = None


def process_next(*, timeout: int = 0) -> ScrivenerRunReport:
    claimed = scrivener_inbox.daemon_claim(timeout=timeout, empty_limit=None)
    if claimed is None:
        return ScrivenerRunReport(claimed=False)

    artifact_key = str(claimed).strip()
    if not artifact_key:
        raise ValueError("scrivener claimed an empty artifact key")

    result = ScrivenerExecutor().execute(artifact_key)
    report = ScrivenerRunReport(
        claimed=True,
        artifact_key=result.artifact_key,
        kind=result.kind,
        table=result.table,
    )
    LOG.info(
        "scrivener operation=persist artifact_key=%s kind=%s table=%s",
        report.artifact_key,
        report.kind,
        report.table,
    )
    return report


def run_forever(*, timeout: int = DEFAULT_CLAIM_TIMEOUT_SECONDS) -> None:
    configure_logging()
    run_daemon(name="scrivener", run_cycle=process_next, timeout=timeout)


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()


__all__ = ["ScrivenerRunReport", "main", "process_next", "run_forever"]
