from __future__ import annotations

"""Ledger writer for export confirmation rows.

DEBT: EXPORTS_TABLE belongs in asc.scrivener.contracts or asc.scrivener.schema
next week with the rest of the table/action contract strings.
"""

from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.queries import CONFIRM_EXPORT_SQL
from asc.scrivener.util import execute_and_commit, timestamp_now
from asc.scrivener.writers.common import insert_row, redis_key


EXPORTS_TABLE = "exports"


def insert_export(*, conn: LedgerConnection, task: object) -> None:
    insert_row(conn, EXPORTS_TABLE, export_values(task))


def confirm_export(*, conn: LedgerConnection, task: object) -> None:
    execute_and_commit(conn, CONFIRM_EXPORT_SQL, confirm_export_values(task))


def export_values(task: object) -> dict[str, Any]:
    key = redis_key(task.source_key)
    return {
        "identity": key.identity,
        "source_identity": key.identity,
        "final_step": int(task.final_step),
        "result_key": task.source_key,
        "exported_at": task.exported_at,
        "export_message": task.export_message,
        "created_at": int(task.created_at),
    }


def confirm_export_values(task: object) -> tuple[Any, ...]:
    key = redis_key(task.source_key)
    return (
        int(timestamp_now()),
        task.export_message,
        key.identity,
    )


def final_step_number(task: object) -> int:
    return int(task.final_step)


def final_result_key(task: object) -> str:
    return task.source_key


__all__ = [
    "EXPORTS_TABLE",
    "confirm_export",
    "confirm_export_values",
    "export_values",
    "final_result_key",
    "final_step_number",
    "insert_export",
]
