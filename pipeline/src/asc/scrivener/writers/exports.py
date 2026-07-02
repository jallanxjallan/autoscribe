"""Ledger writer for terminal call export rows."""

from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.queries import CONFIRM_EXPORT_SQL
from asc.ledger.util import execute_and_commit, timestamp_now
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
        "final_step": final_step_number(task),
        "result_key": task_record_key_text(task),
        "exported_at": int(timestamp_now()),
        "export_message": export_message(task),
        "created_at": int(task.created_at),
    }


def confirm_export_values(task: Any) -> tuple[Any, ...]:
    return (
        int(timestamp_now()),
        export_message(task),
        task_call_identity(task),
    )


def final_step_number(task: Any) -> int:
    key_text = task_record_key_text(task)
    suffix = key_text.rsplit(":", 1)[-1]
    return int(suffix)


def final_result_key(task: Any) -> str:
    return task_record_key_text(task)


def export_message(task: Any) -> str:
    action = "" if task.action is None else str(task.action).strip()
    if action == "call_failed":
        return "failed"
    if action == "call_completed":
        return "completed"
    return action


__all__ = [
    "EXPORTS_TABLE",
    "confirm_export",
    "confirm_export_values",
    "export_message",
    "export_values",
    "final_result_key",
    "final_step_number",
    "insert_export",
]
