from __future__ import annotations

import logging
from typing import Any

from asc.ledger.connect import LedgerConnection

from asc.orchestrator.queues import claim_start, enqueue_worker, requeue_start
from asc.orchestrator.state import load_call_state, mark_started, save_call_state
from asc.orchestrator.verify import verify_input_artifact

log = logging.getLogger(__name__)


def handle_call_start(*, conn: LedgerConnection, call_state_key: str) -> str:
    """Ledger a materialized call_state and stage it for worker execution.

    Enqueue materializes the runtime artifacts and submits the call_state key.
    Orchestrator verifies the source artifact and hands the same call_state key
    to the worker queue.  It does not create or enqueue runtime step keys.
    """

    call_state = load_call_state(call_state_key)
    verify_input_artifact(call_state)
    _insert_call_record(conn=conn, call_state=call_state)
    mark_started(call_state)
    save_call_state(call_state)
    enqueue_worker(call_state_key)
    return call_state_key


class StartOrchestrator:
    """Claim one submitted call_state and release it to worker custody."""

    def __init__(self, *, conn: LedgerConnection | None = None):
        self._conn = conn or LedgerConnection()

    def run(self) -> int:
        claimed = claim_start()
        if claimed is None:
            return 0

        try:
            handle_call_start(conn=self._conn, call_state_key=claimed.identity)
            _commit(self._conn)
        except Exception:
            _rollback(self._conn)
            raise
        return 1


def _insert_call_record(*, conn: LedgerConnection, call_state: Any) -> None:
    """Insert the call ledger row through whatever adapter exists in-tree."""

    try:
        from asc.ledger.records.call import insert_call_record_with_connection
    except ModuleNotFoundError:
        return

    # Newer call_state models may already be acceptable to the call ledger.
    try:
        insert_call_record_with_connection(conn=conn, call=call_state, commit=False)
        return
    except TypeError:
        pass

    # Older ledgers expect a RuntimeCallRecord.  Try loading via a pointer on
    # call_state; otherwise leave ledgering to later migration rather than
    # blocking the artifact-first runtime path.
    call_key = None
    for name in ("call_key", "runtime_call_key"):
        value = getattr(call_state, name, None)
        if value:
            call_key = str(value)
            break
    if call_key is None:
        return

    try:
        from asc.models.runtime.call import RuntimeCallRecord
    except ModuleNotFoundError:
        return

    for method_name in ("load_from_key", "load"):
        method = getattr(RuntimeCallRecord, method_name, None)
        if callable(method):
            call = method(call_key)
            insert_call_record_with_connection(conn=conn, call=call, commit=False)
            return


def _commit(conn: LedgerConnection) -> None:
    commit = getattr(conn, "commit", None)
    if callable(commit):
        commit()


def _rollback(conn: LedgerConnection) -> None:
    rollback = getattr(conn, "rollback", None)
    if callable(rollback):
        rollback()


__all__ = ["StartOrchestrator", "handle_call_start", "requeue_start"]
