"""Ledger writes used by Scrivener."""

from __future__ import annotations

from typing import Any

from asc.ledger.connect import LedgerConnection, connect
from asc.ledger.schema import ensure_ledger_schema
from asc.scrivener.writers.calls import CALLS_TABLE, insert_call
from asc.scrivener.writers.exports import EXPORTS_TABLE, confirm_export, insert_export
from asc.scrivener.writers.steps import STEPS_TABLE, insert_step


CALL_ACTION = "write_call"
STEP_ACTION = "write_step"
EXPORT_ACTION = "call_completed"
CONFIRM_EXPORT_ACTION = "confirm_export"
CALL_FAILED_ACTION = "call_failed"


ACTION_TABLES = {
    CALL_ACTION: CALLS_TABLE,
    STEP_ACTION: STEPS_TABLE,
    EXPORT_ACTION: EXPORTS_TABLE,
    CALL_FAILED_ACTION: EXPORTS_TABLE,
    CONFIRM_EXPORT_ACTION: EXPORTS_TABLE,
}


def table_for(task: Any) -> str:
    action = _required_text(task.action, "action")
    table = _required_text(task.table, "table")
    expected_table = ACTION_TABLES[action]
    if table != expected_table:
        raise ValueError(
            f"scrivener task table/action mismatch: action={action!r} "
            f"table={table!r} expected={expected_table!r}"
        )
    return table


def write_task(task: object) -> None:
    with connect() as conn:
        ensure_ledger_schema(conn)
        write_task_with_connection(conn=conn, task=task)


def write_task_with_connection(*, conn: LedgerConnection, task: object) -> None:
    action = _required_text(task.action, "action")
    table_for(task)

    if action == CALL_ACTION:
        insert_call(conn=conn, task=task)
        return

    if action == STEP_ACTION:
        insert_step(conn=conn, task=task)
        return

    if action in {EXPORT_ACTION, CALL_FAILED_ACTION}:
        insert_export(conn=conn, task=task)
        return

    if action == CONFIRM_EXPORT_ACTION:
        confirm_export(conn=conn, task=task)
        return

    expected = ", ".join(sorted(ACTION_TABLES))
    raise ValueError(f"unknown scrivener task action {action!r}; expected one of: {expected}")


def _required_text(value: object, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    return text


__all__ = [
    "CALL_ACTION",
    "CALL_FAILED_ACTION",
    "CONFIRM_EXPORT_ACTION",
    "EXPORT_ACTION",
    "STEP_ACTION",
    "table_for",
    "write_task",
    "write_task_with_connection",
]
