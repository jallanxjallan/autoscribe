from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.result import insert_result_record_with_connection
from asc.ledger.records.step import insert_step_record_with_connection
from asc.ledger.util import model_value
from asc.models.runtime.result import StepResultRecord
from asc.state.orchestrator_queue import claim_next, enqueue as requeue_completed_step

log = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 0.25

NextStepKeyLookup = Callable[[str, int], str | None]
StepQueueEnqueue = Callable[[str], None]


class OrchestratorContractError(RuntimeError):
    """Raised when a completed-step signal violates pipeline invariants."""


class ScrivenerContractError(OrchestratorContractError):
    """Backward-compatible alias for older imports."""


def _load_persistable_result(completed_signal: str) -> StepResultRecord:
    """Load the runtime result for a completed-step signal.

    Current workers may still place the result identity on the response queue.
    In the new routing model, the queue item should be the step key and the
    response key should be derived from that step key/sequence. Keeping this
    adapter as the single loading point makes the next worker/enqueue refactor
    local to this function.
    """

    return StepResultRecord.load(completed_signal)


def _default_next_step_key(call_identity: str, next_step_number: int) -> str | None:
    """Return the pre-created runtime key for the next step, if it exists.

    The state package owns Redis key/index details. This function is only the
    adapter from orchestrator policy to state lookup.
    """

    try:
        from asc.state.step_index import hget  # type: ignore[attr-defined]

        value = hget(call_identity, next_step_number)
    except ImportError:
        try:
            from asc.state.step_index import get as hget  # type: ignore[attr-defined]

            value = hget(call_identity, next_step_number)
        except ImportError:
            return None

    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _default_enqueue_step(step_key: str) -> None:
    """Enqueue a pre-created runtime step key for worker execution."""

    from asc.state.step_queue import enqueue

    enqueue(step_key)


def _is_successful_step(result: StepResultRecord) -> bool:
    return model_value(result, "content", "response") is not None


class Orchestrator:
    """Single serial pipeline coordinator.

    Workers execute one step and write one response. The orchestrator drains the
    completed-step queue, persists the step outcome, and performs the only
    routing decision in the pipeline: enqueue the next pre-created step, record
    a terminal result, or leave a failed call stopped for inspection.
    """

    def __init__(
        self,
        *,
        conn: LedgerConnection,
        idle_sleep_seconds: float = IDLE_SLEEP_SECONDS,
        next_step_key: NextStepKeyLookup | None = None,
        enqueue_step: StepQueueEnqueue | None = None,
    ):
        self._conn = conn
        self._idle_sleep_seconds = float(idle_sleep_seconds)
        self._next_step_key = next_step_key or _default_next_step_key
        self._enqueue_step = enqueue_step or _default_enqueue_step
        self._drain_then_stop = False
        self._running = False

    def stop(self) -> None:
        self._drain_then_stop = True

    def close(self) -> None:
        self._conn.close()

    def is_running(self) -> bool:
        return self._running

    def run(self, result: StepResultRecord) -> None:
        call_identity = str(model_value(result, "call_identity"))
        step_number = int(model_value(result, "step_number"))

        try:
            step_id = insert_step_record_with_connection(
                conn=self._conn,
                result=result,
                commit=False,
            )

            if _is_successful_step(result):
                next_key = self._next_step_key(call_identity, step_number + 1)
                if next_key is not None:
                    self._enqueue_step(next_key)
                else:
                    insert_result_record_with_connection(
                        conn=self._conn,
                        result=result,
                        terminal_step_id=step_id,
                        commit=False,
                    )

            self._conn.commit()
        except Exception:
            rollback = getattr(self._conn, "rollback", None)
            if rollback is not None:
                rollback()
            raise

    def run_forever(self) -> None:
        self._running = True

        try:
            while True:
                claimed = claim_next()

                if claimed is None:
                    if self._drain_then_stop:
                        log.info("Orchestrator queue drained; stopping")
                        break

                    time.sleep(self._idle_sleep_seconds)
                    continue

                completed_signal = claimed.identity
                score = claimed.score

                try:
                    result = _load_persistable_result(completed_signal)
                    self.run(result)

                except OrchestratorContractError:
                    log.exception(
                        "Orchestrator dropped invalid completed-step signal %s",
                        completed_signal,
                    )

                except Exception:
                    log.exception(
                        "Orchestrator failed processing completed-step signal %s",
                        completed_signal,
                    )
                    try:
                        requeue_completed_step(completed_signal, score=score)
                    except Exception:
                        log.exception(
                            "Orchestrator failed to requeue %s",
                            completed_signal,
                        )
        finally:
            self._running = False


class Scrivener(Orchestrator):
    """Backward-compatible alias for older callers."""


__all__ = [
    "IDLE_SLEEP_SECONDS",
    "NextStepKeyLookup",
    "Orchestrator",
    "OrchestratorContractError",
    "Scrivener",
    "ScrivenerContractError",
    "StepQueueEnqueue",
]
