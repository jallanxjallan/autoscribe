from typing import Any

from asc.scrivener.connect import LedgerConnection, connect
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.writers.calls import insert_call
from asc.scrivener.writers.common import task_action
from asc.scrivener.writers.exports import confirm_export, insert_export
from asc.scrivener.writers.steps import insert_step



CALL_ACTION = "write_call"
STEP_ACTION = "write_step"
EXPORT_ACTION = "call_completed"
CONFIRM_EXPORT_ACTION = "confirm_export"


def write_task(task: object) -> None:
    with connect() as conn:
        write_task_with_connection(conn=conn, task=task)


def write_task_with_connection(*, conn: LedgerConnection, task: Any) -> None:
    ensure_ledger_schema(conn)
    action = task_action(task)

    if action == CALL_ACTION:
        insert_call(conn=conn, task=task)
        return
    if action == STEP_ACTION:
        insert_step(conn=conn, task=task)
        return
    if action == EXPORT_ACTION:
        insert_export(conn=conn, task=task)
        return
    if action == CONFIRM_EXPORT_ACTION:
        confirm_export(conn=conn, task=task)
        return

    expected = ", ".join(
        (CALL_ACTION, STEP_ACTION, EXPORT_ACTION, CONFIRM_EXPORT_ACTION)
    )
    raise ValueError(f"unknown scrivener task action: {action}; expected one of: {expected}")




__all__ = [
    "CALL_ACTION",
    "CONFIRM_EXPORT_ACTION",
    "EXPORT_ACTION",
    "STEP_ACTION",
    "write_task",
    "write_task_with_connection",
]
