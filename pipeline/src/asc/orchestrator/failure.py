from __future__ import annotations

import logging
from typing import Any

from asc.ledger.connect import LedgerConnection

from asc.orchestrator.state import failure_message, mark_failed, save_call_state

log = logging.getLogger(__name__)


def handle_failure(*, conn: LedgerConnection, call_state: Any) -> None:
    """Persist terminal worker failure after worker-scoped retries are exhausted."""

    _insert_failure_record(conn=conn, call_state=call_state)
    mark_failed(call_state)
    save_call_state(call_state)
    log.warning("Recorded terminal worker failure: %s", failure_message(call_state))


def _insert_failure_record(*, conn: LedgerConnection, call_state: Any) -> None:
    for module_name, function_name in (
        ("asc.ledger.records.failure", "insert_failure_record_with_connection"),
        ("asc.ledger.records.step", "insert_failed_step_record_with_connection"),
        ("asc.ledger.records.step", "insert_step_record_with_connection"),
    ):
        try:
            module = __import__(module_name, fromlist=[function_name])
        except ModuleNotFoundError:
            continue
        function = getattr(module, function_name, None)
        if not callable(function):
            continue
        try:
            function(conn=conn, call_state=call_state, commit=False)
            return
        except TypeError:
            try:
                function(
                    conn=conn,
                    result=getattr(call_state, "worker_report", call_state),
                    commit=False,
                )
                return
            except TypeError:
                continue
