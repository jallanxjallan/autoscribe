from __future__ import annotations

import logging
from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.queues import claim_orchestrator_pending, claim_outcome
from asc.orchestrator.receive import handle_orchestrator_signal
from asc.orchestrator.signals import ORCHESTRATOR_PENDING, WORKER_OUTCOME

log = logging.getLogger(__name__)

OUTCOME_BLOCK_TIMEOUT_SECONDS = 1
PENDING_BLOCK_TIMEOUT_SECONDS = 1
MAX_PENDING_CURSORS_PER_TICK = 100


class OrchestratorDaemon:
    """Long-lived orchestrator over blocking custody queues.

    Normal custody moves through Redis LIST queues:

    - state:orchestrator:pending
    - state:worker:pending
    - state:worker:outcome

    The active cursor index remains a passive observability/recovery index. It is
    updated by queue helpers, but this daemon does not inspect it, lease it,
    retry from it, or requeue from it.
    """

    def __init__(
        self,
        *,
        ledger: LedgerConnection | None = None,
        outcome_block_timeout_seconds: int = OUTCOME_BLOCK_TIMEOUT_SECONDS,
        pending_block_timeout_seconds: int = PENDING_BLOCK_TIMEOUT_SECONDS,
        max_pending_cursors_per_tick: int = MAX_PENDING_CURSORS_PER_TICK,
    ) -> None:
        self.ledger = ledger or LedgerConnection()
        self.outcome_block_timeout_seconds = int(outcome_block_timeout_seconds)
        self.pending_block_timeout_seconds = int(pending_block_timeout_seconds)
        self.max_pending_cursors_per_tick = int(max_pending_cursors_per_tick)

    def run_forever(self) -> None:
        while True:
            self.run_once_blocking()

    def run_once_blocking(self) -> int:
        """Process one blocking foreground tick and return custody work touched."""
        processed = 0

        outcome = claim_outcome(block=True, timeout=self.outcome_block_timeout_seconds)
        if outcome is not None:
            self._process_signal(outcome, source=WORKER_OUTCOME)
            processed += 1
            processed += self._drain_foreground()
            return processed

        pending = claim_orchestrator_pending(
            limit=self.max_pending_cursors_per_tick,
            block=True,
            timeout=self.pending_block_timeout_seconds,
        )
        for signal in pending:
            self._process_signal(signal, source=ORCHESTRATOR_PENDING)
            processed += 1

        if processed:
            processed += self._drain_foreground()

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
            self._process_signal(outcome, source=WORKER_OUTCOME)
            processed += 1

        for signal in claim_orchestrator_pending(limit=self.max_pending_cursors_per_tick):
            self._process_signal(signal, source=ORCHESTRATOR_PENDING)
            processed += 1

        return processed

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
            return


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
    "MAX_PENDING_CURSORS_PER_TICK",
    "OrchestratorDaemon",
    "OUTCOME_BLOCK_TIMEOUT_SECONDS",
    "PENDING_BLOCK_TIMEOUT_SECONDS",
]
