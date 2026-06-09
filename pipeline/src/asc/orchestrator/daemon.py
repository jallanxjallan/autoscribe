from __future__ import annotations

import logging
import time

from asc.ledger.connect import LedgerConnection
from asc.ledger.util import model_value
from asc.models.runtime.result import StepResultRecord
from asc.state.orchestrator_queue import claim_next, enqueue as requeue_completed_step

from asc.orchestrator.failure import handle_failure
from asc.orchestrator.retry import decide_retry
from asc.orchestrator.routing import (
    NextStepKeyLookup,
    OrchestratorContractError,
    ScrivenerContractError,
    StepQueueEnqueue,
    default_enqueue_step,
    default_next_step_key,
)
from asc.orchestrator.success import handle_success
from asc.orchestrator.start import handle_call_start

log = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 0.25


def load_persistable_result(completed_signal: str) -> StepResultRecord:
    """Load the runtime result for a completed-step signal.

    Current workers may still place the result identity on the response queue.
    In the new routing model, the queue item should be the step key and the
    response key should be derived from that step key/sequence. Keeping this
    adapter as the single loading point makes the next worker/enqueue refactor
    local to this function.
    """

    return StepResultRecord.load(completed_signal)


def is_successful_step(result: StepResultRecord) -> bool:
    return model_value(result, "content", "response") is not None




def claim_next_call_start():
    for module_name in (
        "asc.state.call_queue",
        "asc.state.orchestrator_call_queue",
        "asc.state.start_queue",
    ):
        try:
            module = __import__(module_name, fromlist=["claim_next"])
        except ImportError:
            continue
        claim = getattr(module, "claim_next", None)
        if callable(claim):
            return claim()
    return None


def requeue_call_start(call_key: str, *, score: object | None = None) -> None:
    for module_name in (
        "asc.state.call_queue",
        "asc.state.orchestrator_call_queue",
        "asc.state.start_queue",
    ):
        try:
            module = __import__(module_name, fromlist=["enqueue"])
        except ImportError:
            continue
        enqueue = getattr(module, "enqueue", None)
        if callable(enqueue):
            try:
                enqueue(call_key, score=score)
            except TypeError:
                enqueue(call_key)
            return
    raise RuntimeError("no orchestrator call queue found")


class Orchestrator:
    """Single serial pipeline coordinator.

    Workers execute one step and write one response. The orchestrator drains the
    completed-step queue, persists the step outcome, and performs the only
    routing decision in the pipeline: enqueue the next pre-created step, record
    a terminal result, or stop a failed call for inspection/retry policy.
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
        self._next_step_key = next_step_key or default_next_step_key
        self._enqueue_step = enqueue_step or default_enqueue_step
        self._drain_then_stop = False
        self._running = False

    def stop(self) -> None:
        self._drain_then_stop = True

    def close(self) -> None:
        self._conn.close()

    def is_running(self) -> bool:
        return self._running

    def run(self, result: StepResultRecord) -> None:
        try:
            if is_successful_step(result):
                handle_success(
                    conn=self._conn,
                    result=result,
                    next_step_key=self._next_step_key,
                    enqueue_step=self._enqueue_step,
                )
            else:
                handle_failure(conn=self._conn, result=result)

            self._conn.commit()
        except Exception:
            rollback = getattr(self._conn, "rollback", None)
            if rollback is not None:
                rollback()
            raise

    def run_start(self, call_key: str) -> None:
        try:
            handle_call_start(
                conn=self._conn,
                call_key=call_key,
                enqueue_step=self._enqueue_step,
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
                started = claim_next_call_start()
                if started is not None:
                    call_key = started.identity
                    score = started.score
                    try:
                        self.run_start(call_key)
                    except OrchestratorContractError:
                        log.exception(
                            "Orchestrator dropped invalid call-start signal %s",
                            call_key,
                        )
                    except Exception as exc:
                        decision = decide_retry(error=exc)
                        log.exception(
                            "Orchestrator failed processing call-start signal %s",
                            call_key,
                        )
                        if decision.should_retry:
                            requeue_call_start(call_key, score=score)
                    continue

                claimed = claim_next()

                if claimed is None:
                    if self._drain_then_stop:
                        log.info("Orchestrator queues drained; stopping")
                        break

                    time.sleep(self._idle_sleep_seconds)
                    continue

                completed_signal = claimed.identity
                score = claimed.score

                try:
                    result = load_persistable_result(completed_signal)
                    self.run(result)

                except OrchestratorContractError:
                    log.exception(
                        "Orchestrator dropped invalid completed-step signal %s",
                        completed_signal,
                    )

                except Exception as exc:
                    decision = decide_retry(error=exc)
                    log.exception(
                        "Orchestrator failed processing completed-step signal %s",
                        completed_signal,
                    )
                    if not decision.should_retry:
                        continue
                    try:
                        if decision.delay_seconds > 0:
                            time.sleep(decision.delay_seconds)
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
    "is_successful_step",
    "claim_next_call_start",
    "load_persistable_result",
    "requeue_call_start",
]
