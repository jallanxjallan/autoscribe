from __future__ import annotations

import logging
import time

from asc.ledger.connect import LedgerConnection
from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.policy import decide_infrastructure_retry
from asc.orchestrator.queues import claim, requeue
from asc.orchestrator.receive import handle_orchestrator_signal

log = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 0.25


class OrchestratorDaemon:
    """Single-queue orchestrator pass over full call_state keys."""

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
        self._conn.close()

    def is_running(self) -> bool:
        return self._running

    def run(self) -> int:
        claimed = claim()
        if claimed is None:
            return 0

        try:
            handle_orchestrator_signal(conn=self._conn, call_state_key=claimed.identity)
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return 1

    def run_forever(self) -> None:
        self._running = True
        try:
            while True:
                claimed = claim()
                if claimed is None:
                    if self._drain_then_stop:
                        log.info("Orchestrator queue drained; stopping")
                        break
                    time.sleep(self._idle_sleep_seconds)
                    continue

                try:
                    handle_orchestrator_signal(conn=self._conn, call_state_key=claimed.identity)
                    self._conn.commit()
                except OrchestratorContractError:
                    self._conn.rollback()
                    log.exception("Dropped invalid call_state signal %s", claimed.identity)
                except Exception as exc:
                    self._conn.rollback()
                    decision = decide_infrastructure_retry(error=exc)
                    log.exception("Infrastructure failure processing %s", claimed.identity)
                    if decision.should_retry:
                        if decision.delay_seconds > 0:
                            time.sleep(decision.delay_seconds)
                        requeue(claimed.identity, score=claimed.score)
        finally:
            self._running = False


__all__ = ["IDLE_SLEEP_SECONDS", "OrchestratorDaemon", "OrchestratorContractError"]
