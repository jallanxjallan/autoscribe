from __future__ import annotations

import logging
import time

from asc.ledger.connect import LedgerConnection

from asc.orchestrator.errors import OrchestratorContractError, ScrivenerContractError
from asc.orchestrator.policy import decide_infrastructure_retry
from asc.orchestrator.queues import claim_response, requeue_response
from asc.orchestrator.receive import handle_worker_response

log = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 0.25


class OrchestratorDaemon:
    """Single-response orchestrator pass over worker-returned call_state keys."""

    def __init__(
        self,
        *,
        conn: LedgerConnection | None = None,
        idle_sleep_seconds: float = IDLE_SLEEP_SECONDS,
    ):
        self._conn = conn or LedgerConnection()
        self._idle_sleep_seconds = float(idle_sleep_seconds)
        self._drain_then_stop = False
        self._running = False

    def stop(self) -> None:
        self._drain_then_stop = True

    def close(self) -> None:
        close = getattr(self._conn, "close", None)
        if callable(close):
            close()

    def is_running(self) -> bool:
        return self._running

    def run(self) -> int:
        claimed = claim_response()
        if claimed is None:
            return 0

        try:
            handle_worker_response(conn=self._conn, call_state_key=claimed.identity)
            _commit(self._conn)
        except Exception:
            _rollback(self._conn)
            raise
        return 1

    def run_forever(self) -> None:
        self._running = True
        try:
            while True:
                claimed = claim_response()
                if claimed is None:
                    if self._drain_then_stop:
                        log.info("Orchestrator response queue drained; stopping")
                        break
                    time.sleep(self._idle_sleep_seconds)
                    continue

                try:
                    handle_worker_response(conn=self._conn, call_state_key=claimed.identity)
                    _commit(self._conn)
                except OrchestratorContractError:
                    _rollback(self._conn)
                    log.exception(
                        "Orchestrator dropped invalid call_state response %s",
                        claimed.identity,
                    )
                except Exception as exc:
                    _rollback(self._conn)
                    decision = decide_infrastructure_retry(error=exc)
                    log.exception(
                        "Orchestrator infrastructure failure processing %s",
                        claimed.identity,
                    )
                    if decision.should_retry:
                        if decision.delay_seconds > 0:
                            time.sleep(decision.delay_seconds)
                        requeue_response(claimed.identity, score=claimed.score)
        finally:
            self._running = False


class Orchestrator(OrchestratorDaemon):
    """Backward-compatible alias for older imports."""


class Scrivener(OrchestratorDaemon):
    """Backward-compatible alias for older imports."""


def _commit(conn: LedgerConnection) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _rollback(conn: LedgerConnection) -> None:
    rollback = getattr(conn, "rollback", None)
    if callable(rollback):
        rollback()


__all__ = [
    "IDLE_SLEEP_SECONDS",
    "OrchestratorDaemon",
    "Orchestrator",
    "Scrivener",
    "OrchestratorContractError",
    "ScrivenerContractError",
]
