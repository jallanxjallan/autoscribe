from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.result import insert_result_record_with_connection
from asc.ledger.records.step import insert_step_record_with_connection
from asc.ledger.util import model_value
from asc.models.runtime.result import StepResultRecord
from asc.state.scrivener_queue import claim_next, enqueue as requeue_result

log = logging.getLogger(__name__)

IDLE_SLEEP_SECONDS = 0.25

ContentIndexHKeys = Callable[[str], Iterable[Any]]


class ScrivenerContractError(RuntimeError):
    """Raised when a queued result is invalid for SQL persistence."""


def _load_persistable_result(result_identity: str) -> StepResultRecord:
    """Load the runtime result queued for Scrivener.

    Both successful and failed step results are persistable. Only a successful
    terminal step result receives a row in the minimal results table.
    """

    return StepResultRecord.load(result_identity)


def _default_content_index_hkeys(call_identity: str) -> Iterable[Any]:
    """Return the hkeys for the call's content index.

    The content-index state module owns the Redis key shape. Scrivener only
    needs the numeric hash fields so it can decide whether a completed step is
    terminal. If the state helper is renamed, this is the single adapter to
    update.
    """

    from asc.state.content_index import hkeys

    return hkeys(call_identity)


def _int_hkey(value: Any) -> int:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return int(value)


def _terminal_step_number_from_content_index(
    *,
    call_identity: str,
    content_index_hkeys: ContentIndexHKeys,
) -> int:
    positions = [_int_hkey(value) for value in content_index_hkeys(call_identity)]
    if not positions:
        raise ScrivenerContractError(
            f"content index for call {call_identity} has no hkeys"
        )

    # Content position 1 is the original prompt. Step N writes content position
    # N + 1, so the terminal step number is max(content_position) - 1.
    terminal_step_number = max(positions) - 1
    if terminal_step_number < 1:
        raise ScrivenerContractError(
            f"content index for call {call_identity} does not contain a step output position"
        )
    return terminal_step_number


def _is_successful_step(result: StepResultRecord) -> bool:
    return model_value(result, "content", "response") is not None


class Scrivener:
    """
    Single serial persistence worker.

    Scrivener drains the runtime result queue. Every queued step result is
    persisted into steps. Only a successful terminal step result creates a row
    in results, which remains a pointer to the terminal step row.
    """

    def __init__(
        self,
        *,
        conn: LedgerConnection,
        idle_sleep_seconds: float = IDLE_SLEEP_SECONDS,
        content_index_hkeys: ContentIndexHKeys | None = None,
    ):
        self._conn = conn
        self._idle_sleep_seconds = float(idle_sleep_seconds)
        self._content_index_hkeys = content_index_hkeys or _default_content_index_hkeys
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
                terminal_step_number = _terminal_step_number_from_content_index(
                    call_identity=call_identity,
                    content_index_hkeys=self._content_index_hkeys,
                )
                if step_number >= terminal_step_number:
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
                        log.info("Scrivener queue drained; stopping")
                        break

                    time.sleep(self._idle_sleep_seconds)
                    continue

                result_identity = claimed.identity
                score = claimed.score

                try:
                    result = _load_persistable_result(result_identity)
                    self.run(result)

                except ScrivenerContractError:
                    log.exception(
                        "Scrivener dropped invalid queued result %s",
                        result_identity,
                    )

                except Exception:
                    log.exception(
                        "Scrivener failed persisting queued result %s",
                        result_identity,
                    )
                    try:
                        requeue_result(result_identity, score=score)
                    except Exception:
                        log.exception(
                            "Scrivener failed to requeue %s",
                            result_identity,
                        )
        finally:
            self._running = False


__all__ = [
    "ContentIndexHKeys",
    "IDLE_SLEEP_SECONDS",
    "Scrivener",
    "ScrivenerContractError",
]
