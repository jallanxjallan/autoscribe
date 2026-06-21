"""Ledger writer for export confirmation rows.

DEBT: EXPORTS_TABLE belongs in asc.scrivener.contracts or asc.scrivener.schema
with the rest of the table/action contract strings.
"""

from typing import Any

from asc.scrivener.connect import LedgerConnection
from asc.scrivener.queries import CONFIRM_EXPORT_SQL
from asc.scrivener.util import execute_and_commit, timestamp_now
from asc.scrivener.writers.common import (
    insert_row,
    optional_domain_identity,
    task_call_identity,
    task_record_key_text,
)


EXPORTS_TABLE = "exports"


def insert_export(*, conn: LedgerConnection, task: object) -> None:
    insert_row(conn, EXPORTS_TABLE, export_values(task))


def confirm_export(*, conn: LedgerConnection, task: object) -> None:
    execute_and_commit(conn, CONFIRM_EXPORT_SQL, confirm_export_values(task))


def export_values(task: Any) -> dict[str, Any]:
    call_identity = task_call_identity(task)
    source_identity = optional_domain_identity(
        task,
        "source_identity",
        "record_identity",
        "document_identity",
    ) or call_identity

    return {
        "identity": call_identity,
        "source_identity": source_identity,
        "final_step": int(task.final_step),
        "result_key": task_record_key_text(task),
        "exported_at": task.exported_at,
        "export_message": task.export_message,
        "created_at": int(task.created_at),
    }


def confirm_export_values(task: Any) -> tuple[Any, ...]:
    return (
        int(timestamp_now()),
        task.export_message,
        task_call_identity(task),
    )


def final_step_number(task: Any) -> int:
    return int(task.final_step)


def final_result_key(task: Any) -> str:
    return task_record_key_text(task)


__all__ = [
    "EXPORTS_TABLE",
    "confirm_export",
    "confirm_export_values",
    "export_values",
    "final_result_key",
    "final_step_number",
    "insert_export",
]
