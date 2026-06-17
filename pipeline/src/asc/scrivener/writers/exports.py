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
    created_at = getattr(task, "created_at", None) or timestamp_now()

    return {
        "identity": ledger_identity(task),
        "source_identity": source_identity(task),
        "final_step": final_step_number(task),
        "result_key": final_result_key(task),
        "exported_at": getattr(task, "exported_at", None),
        "export_message": getattr(task, "export_message", None),
        "created_at": int(created_at),
    }


def confirm_export_values(task: object) -> tuple[Any, ...]:
    return (
        int(getattr(task, "exported_at", None) or timestamp_now()),
        getattr(task, "export_message", None),
        ledger_identity(task),
    )


def final_step_number(task: object) -> int:
    explicit = getattr(task, "final_step", None)
    if explicit not in (None, ""):
        return int(explicit)

    number = step_number(task)
    if number > 0:
        return number

    raise ValueError("export task missing final step number")


def final_result_key(task: object) -> str:
    explicit = getattr(task, "result_key", None)
    if explicit:
        return str(explicit)

    return source_key(task)


__all__ = [
    "confirm_export",
    "confirm_export_values",
    "export_values",
    "final_result_key",
    "final_step_number",
    "insert_export",
]