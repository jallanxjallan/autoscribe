from __future__ import annotations

from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.records.result import (
    insert_result_record_with_connection,
    read_result_record_by_call_with_connection,
)
from asc.ledger.records.step import read_step_records_for_call_with_connection
from asc.models.runtime.cursor import RuntimeCursor
from asc.orchestrator.errors import OrchestratorContractError
from asc.orchestrator.queues import bump_terminal_cursor
from asc.runtime.response_index import response_index


def record_terminal_result(*, ledger: LedgerConnection, cursor_key: str) -> None:
    """Persist the terminal result row for a completed runtime call.

    The ledger's results table is only a pointer: one result identity, one call,
    and the SQL step_id for the successful terminal step. The terminal step row
    already owns the final response content used by export views.
    """
    cursor = RuntimeCursor.load(cursor_key)

    existing = read_result_record_by_call_with_connection(
        conn=ledger,
        call_identity=cursor.identity,
    )
    if existing is not None:
        return

    terminal_step = _terminal_step_row(ledger=ledger, cursor=cursor)
    result = _result_pointer(cursor=cursor, terminal_step=terminal_step)

    insert_result_record_with_connection(
        conn=ledger,
        result=result,
        terminal_step_id=int(terminal_step["step_id"]),
    )


def close_terminal_cursor(*, ledger: LedgerConnection, cursor_key: str) -> str:
    """Record terminal state and move the cursor out of active rotation."""
    # Future production note:
    # inspect failure models here as well. Successful terminal steps write a
    # result pointer; failed terminal steps should be routed through retry/fail
    # policy instead of pretending an exportable result exists.
    record_terminal_result(ledger=ledger, cursor_key=cursor_key)
    bump_terminal_cursor(cursor_key)
    return "terminal-recorded"


def _terminal_step_row(
    *,
    ledger: LedgerConnection,
    cursor: RuntimeCursor,
) -> dict[str, Any]:
    slots = response_index(cursor.response_index_key)
    if not slots:
        raise OrchestratorContractError(
            f"response index is missing or empty: {cursor.response_index_key}"
        )

    empty_slots = [slot for slot, value in slots.items() if not str(value).strip()]
    if empty_slots:
        raise OrchestratorContractError(
            f"cursor is not terminal; empty response slots remain: "
            f"{cursor.response_index_key} slots={empty_slots}"
        )

    terminal_step_number = max(slots)
    if terminal_step_number < 1:
        raise OrchestratorContractError(
            f"response index has no worker output slots: {cursor.response_index_key}"
        )

    rows = read_step_records_for_call_with_connection(
        conn=ledger,
        call_identity=cursor.identity,
    )
    matches = [
        row
        for row in rows
        if int(row.get("step_number") or 0) == terminal_step_number
    ]
    if not matches:
        raise OrchestratorContractError(
            f"no ledger step row for terminal step "
            f"call={cursor.identity} step={terminal_step_number}"
        )

    row = matches[-1]
    status = str(row.get("status") or "")
    if status != "completed":
        detail = row.get("fail_message") or "terminal step did not complete"
        raise OrchestratorContractError(
            f"terminal step is not successful: "
            f"call={cursor.identity} step={terminal_step_number} "
            f"status={status!r} detail={detail!r}"
        )

    if row.get("response") is None:
        raise OrchestratorContractError(
            f"terminal completed step has no response content: "
            f"call={cursor.identity} step={terminal_step_number}"
        )

    return row


def _result_pointer(
    *,
    cursor: RuntimeCursor,
    terminal_step: dict[str, Any],
) -> dict[str, Any]:
    """Build the ledger-facing result object.

    The result writer only requires model_value-compatible fields. Use a dict so
    this terminal path is not coupled to the worker payload model name while the
    runtime result models are still settling.
    """
    completed_at = terminal_step.get("completed_at") or terminal_step.get("created_at")
    return {
        "identity": cursor.identity,
        "result_identity": cursor.identity,
        "call_identity": cursor.identity,
        "content": terminal_step.get("response"),
        "response": terminal_step.get("response"),
        "completed_at": completed_at,
        "created_at": completed_at,
    }


__all__ = [
    "close_terminal_cursor",
    "record_terminal_result",
]
