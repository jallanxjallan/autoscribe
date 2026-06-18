from __future__ import annotations

from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.queries import CONFIRM_EXPORT_SQL
from asc.scrivener.util import execute_and_commit, timestamp_now
from asc.scrivener.writers.common import insert_row, ledger_identity, source_identity, source_key, step_number


def insert_export(*, conn: LedgerConnection, task: object) -> None:
    insert_row(conn, "exports", export_values(task))


def confirm_export(*, conn: LedgerConnection, task: object) -> None:
    execute_and_commit(conn, CONFIRM_EXPORT_SQL, confirm_export_values(task))


def export_values(task: object) -> dict[str, Any]:
    return {
        "identity": ledger_identity(task),
        "source_identity": source_identity(task),
        "final_step": final_step_number(task),
        "result_key": final_result_key(task),
        "exported_at": task.exported_at,
        "export_message": task.export_message,
        "created_at": int(task.created_at),
    }


def confirm_export_values(task: object) -> tuple[Any, ...]:
    return (
        int(timestamp_now()),
        task.export_message,
        ledger_identity(task),
    )


def final_step_number(task: object) -> int:
    return int(task.final_step)


def final_result_key(task: object) -> str:
    return source_key(task)


__all__ = [
    "confirm_export",
    "confirm_export_values",
    "export_values",
    "final_result_key",
    "final_step_number",
    "insert_export",
]
