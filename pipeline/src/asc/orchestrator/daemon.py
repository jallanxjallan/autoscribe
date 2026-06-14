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

OUTCOME_BLOCK_TIMEOUT_SECONDS = 1
PENDING_BLOCK_TIMEOUT_SECONDS = 1
MAX_PENDING_CURSORS_PER_TICK = 100
MAX_STALE_CURSORS_PER_TICK = 25
ACTIVE_STALE_AFTER_SECONDS = 30.0
ACTIVE_INSPECTION_LEASE_SECONDS = 30.0
ACTIVE_WATCHDOG_INTERVAL_SECONDS = 5.0


class OrchestratorDaemon:
    """Long-lived orchestrator over blocking custody queues plus watchdog.

    Normal custody moves through Redis LIST queues:

    - state:orchestrator:pending
    - state:worker:pending
    - state:worker:outcome

    state:runtime:active remains a passive ZSET monitoring/recovery index. It is
    inspected on a timer only, and never drives the main loop hot.
    """

    def __init__(
        self,
        *,
        ledger: LedgerConnection | None = None,
        outcome_block_timeout_seconds: int = OUTCOME_BLOCK_TIMEOUT_SECONDS,
        pending_block_timeout_seconds: int = PENDING_BLOCK_TIMEOUT_SECONDS,
        max_pending_cursors_per_tick: int = MAX_PENDING_CURSORS_PER_TICK,
        max_stale_cursors_per_tick: int = MAX_STALE_CURSORS_PER_TICK,
        active_stale_after_seconds: float = ACTIVE_STALE_AFTER_SECONDS,
        active_inspection_lease_seconds: float = ACTIVE_INSPECTION_LEASE_SECONDS,
        active_watchdog_interval_seconds: float = ACTIVE_WATCHDOG_INTERVAL_SECONDS,
    ) -> None:
        self.ledger = ledger or LedgerConnection()
        self.outcome_block_timeout_seconds = int(outcome_block_timeout_seconds)
        self.pending_block_timeout_seconds = int(pending_block_timeout_seconds)
        self.max_pending_cursors_per_tick = int(max_pending_cursors_per_tick)
        self.max_stale_cursors_per_tick = int(max_stale_cursors_per_tick)
        self.active_stale_after_seconds = float(active_stale_after_seconds)
        self.active_inspection_lease_seconds = float(active_inspection_lease_seconds)
        self.active_watchdog_interval_seconds = float(active_watchdog_interval_seconds)
        self._next_watchdog_at = time.monotonic() + self.active_watchdog_interval_seconds

    def run_forever(self) -> None:
        while True:
            self.run_once_blocking()

    def run_once_blocking(self) -> int:
        """Process one blocking foreground tick and return custody work touched."""
        processed = 0

        # Prefer completed worker outcomes so finished work advances promptly.
        outcome = claim_outcome(block=True, timeout=self.outcome_block_timeout_seconds)
        if outcome is not None:
            self._process_signal(outcome, source="worker_outcome")
            processed += 1
            processed += self._drain_foreground()
            self._run_watchdog_if_due()
            return processed

        # If no outcome arrived, block briefly for newly enqueued calls/retries.
        pending = claim_orchestrator_pending(
            limit=self.max_pending_cursors_per_tick,
            block=True,
            timeout=self.pending_block_timeout_seconds,
        )
        for signal in pending:
            self._process_signal(signal, source="orchestrator_pending")
            processed += 1

        if processed:
            processed += self._drain_foreground()

        self._run_watchdog_if_due()
        return processed

    def run_once(self) -> int:
        """Compatibility alias for old CLI/tests."""
        return self.run_once_blocking()

    def _drain_foreground(self) -> int:
        """Drain immediately available live custody work without blocking."""
        processed = 0

        while True:
            outcome = claim_outcome()
            if outcome is None:
                break
            self._process_signal(outcome, source="worker_outcome")
            processed += 1

        for signal in claim_orchestrator_pending(limit=self.max_pending_cursors_per_tick):
            self._process_signal(signal, source="orchestrator_pending")
            processed += 1

        return processed

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
            if decision.should_retry:
                requeue(cursor_key, delay_seconds=decision.delay_seconds)
                return
            raise


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
    "MAX_PENDING_CURSORS_PER_TICK",
    "MAX_STALE_CURSORS_PER_TICK",
    "OrchestratorDaemon",
    "OUTCOME_BLOCK_TIMEOUT_SECONDS",
    "PENDING_BLOCK_TIMEOUT_SECONDS",
]
