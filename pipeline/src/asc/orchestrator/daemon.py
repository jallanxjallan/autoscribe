from __future__ import annotations

import logging
import time
from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.policy import decide_infrastructure_retry
from asc.orchestrator.queues import (
    claim_active_stale,
    claim_orchestrator_pending,
    claim_outcome,
    requeue,
)
from asc.orchestrator.receive import handle_orchestrator_signal

log = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 0.5
MAX_PENDING_CURSORS_PER_TICK = 100
MAX_STALE_CURSORS_PER_TICK = 25
ACTIVE_STALE_AFTER_SECONDS = 30.0
ACTIVE_INSPECTION_LEASE_SECONDS = 30.0
ACTIVE_WATCHDOG_INTERVAL_SECONDS = 5.0


class OrchestratorDaemon:
    """Long-lived orchestrator over real custody queues plus passive monitoring.

    Normal custody moves through queues:

    - state:orchestrator:pending
    - state:worker:pending
    - state:worker:outcome

    state:runtime:active is only a passive monitoring/recovery index. It must
    never make the daemon loop hot. The watchdog is therefore rate-limited and
    watchdog observations do not count as foreground work.
    """

    def __init__(
        self,
        *,
        ledger: LedgerConnection | None = None,
        idle_sleep_seconds: float = IDLE_SLEEP_SECONDS,
        max_pending_cursors_per_tick: int = MAX_PENDING_CURSORS_PER_TICK,
        max_stale_cursors_per_tick: int = MAX_STALE_CURSORS_PER_TICK,
        active_stale_after_seconds: float = ACTIVE_STALE_AFTER_SECONDS,
        active_inspection_lease_seconds: float = ACTIVE_INSPECTION_LEASE_SECONDS,
        active_watchdog_interval_seconds: float = ACTIVE_WATCHDOG_INTERVAL_SECONDS,
    ) -> None:
        self.ledger = ledger or LedgerConnection()
        self.idle_sleep_seconds = float(idle_sleep_seconds)
        self.max_pending_cursors_per_tick = int(max_pending_cursors_per_tick)
        self.max_stale_cursors_per_tick = int(max_stale_cursors_per_tick)
        self.active_stale_after_seconds = float(active_stale_after_seconds)
        self.active_inspection_lease_seconds = float(active_inspection_lease_seconds)
        self.active_watchdog_interval_seconds = float(active_watchdog_interval_seconds)
        self._next_watchdog_at = time.monotonic() + self.active_watchdog_interval_seconds

    def run_once(self) -> int:
        """Process one foreground tick and return real custody work touched.

        The passive active-index watchdog may also run, but watchdog-only work is
        intentionally not included in the return value. This guarantees the main
        loop still sleeps when no pending/outcome queue work exists.
        """
        processed = 0

        outcome = claim_outcome()
        if outcome is not None:
            self._process_signal(outcome, source="worker_outcome")
            processed += 1

        for signal in claim_orchestrator_pending(limit=self.max_pending_cursors_per_tick):
            self._process_signal(signal, source="orchestrator_pending")
            processed += 1

        self._run_watchdog_if_due()
        return processed

    def run_forever(self) -> None:
        while True:
            processed = self.run_once()
            if processed == 0:
                time.sleep(self.idle_sleep_seconds)

    def _run_watchdog_if_due(self) -> None:
        now = time.monotonic()
        if now < self._next_watchdog_at:
            return

        self._next_watchdog_at = now + self.active_watchdog_interval_seconds
        for signal in claim_active_stale(
            limit=self.max_stale_cursors_per_tick,
            stale_after_seconds=self.active_stale_after_seconds,
            lease_seconds=self.active_inspection_lease_seconds,
        ):
            self._process_signal(signal, source="active_watchdog")

    def _process_signal(self, claimed: Any, *, source: str) -> None:
        cursor_key = _claimed_identity(claimed)
        try:
            result = handle_orchestrator_signal(
                ledger=self.ledger,
                cursor_key=cursor_key,
                source=source,
            )
            log.info("orchestrator source=%s cursor=%s result=%s", source, cursor_key, result)
        except OrchestratorContractError:
            log.exception("Dropped invalid runtime cursor signal %s from %s", cursor_key, source)
            raise
        except Exception as exc:
            decision = decide_infrastructure_retry(error=exc)
            log.exception("Infrastructure failure processing %s from %s", cursor_key, source)
            raise
            if decision.should_retry:
                requeue(cursor_key, delay_seconds=decision.delay_seconds)


def _claimed_identity(claimed: Any) -> str:
    value = getattr(claimed, "cursor_key", None)
    if value is None:
        value = getattr(claimed, "identity", None)
    if value is None:
        value = getattr(claimed, "key", None)
    if value is None:
        value = claimed
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str) or not value.strip():
        raise OrchestratorContractError(
            "orchestrator signal must provide a full RuntimeCursor key"
        )
    return value.strip()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    OrchestratorDaemon().run_forever()


if __name__ == "__main__":
    main()


__all__ = [
    "ACTIVE_INSPECTION_LEASE_SECONDS",
    "ACTIVE_STALE_AFTER_SECONDS",
    "ACTIVE_WATCHDOG_INTERVAL_SECONDS",
    "IDLE_SLEEP_SECONDS",
    "MAX_PENDING_CURSORS_PER_TICK",
    "MAX_STALE_CURSORS_PER_TICK",
    "OrchestratorDaemon",
]
