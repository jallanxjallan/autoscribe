"""Scrivener daemon entrypoint."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from asc.scrivener import inbox as scrivener_inbox
from asc.scrivener.execute import ScrivenerExecutor
from asc.models.process.result import record_failure
from asc.state.daemon import DEFAULT_CLAIM_TIMEOUT_SECONDS, configure_logging, run_daemon
from asc.redis.key import RedisKey


LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScrivenerRunReport:
    claimed: bool
    artifact_key: str | None = None
    kind: str | None = None
    table: str | None = None
    failure_key: str | None = None


def process_next(*, timeout: int = 0) -> ScrivenerRunReport:
    claimed = scrivener_inbox.daemon_claim(timeout=timeout, empty_limit=None)
    if claimed is None:
        return ScrivenerRunReport(claimed=False)

    artifact_key = str(claimed).strip()
    if not artifact_key:
        raise ValueError("scrivener claimed an empty artifact key")

    try:
        result = ScrivenerExecutor().execute(artifact_key)
    except Exception as exc:
        process_identity = None
        try:
            process_identity = RedisKey(artifact_key).identity
        except Exception:
            pass
        failure_key = record_failure(
            stage="scrivener.persist",
            exc=exc,
            process_identity=process_identity,
            artifact_key=artifact_key,
        )
        LOG.error(
            "scrivener operation=failed artifact_key=%s failure_key=%s",
            artifact_key,
            failure_key,
        )
        return ScrivenerRunReport(
            claimed=True,
            artifact_key=artifact_key,
            failure_key=failure_key,
        )

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
