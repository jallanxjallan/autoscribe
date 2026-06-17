from __future__ import annotations

from typing import Any

from asc.scrivener.connect import LedgerConnection, connect
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.util import timestamp_now
from asc.scrivener.writers.common import (
    insert_row,
    ledger_identity,
    load_task_input,
    model_json,
    source_identity,
)


def insert_call_from_task(task: object) -> None:
    with connect() as conn:
        insert_call_from_task_with_connection(conn=conn, task=task)


def insert_call_from_task_with_connection(*, conn: LedgerConnection, task: object) -> None:
    ensure_ledger_schema(conn)
    insert_call(conn=conn, task=task)


def insert_call(*, conn: LedgerConnection, task: object) -> None:
    record = load_task_input(task)
    insert_row(conn, "calls", call_values(task, record))


def call_values(task: object, record: object | None = None) -> dict[str, Any]:
    if record is None:
        record = load_task_input(task)

    created_at = getattr(record, "created_at", None) or getattr(task, "created_at", None) or timestamp_now()

    return {
        "identity": ledger_identity(task),
        "source_identity": source_identity(task),
        "source_json": model_json(record),
        "created_at": int(created_at),
    }


__all__ = [
    "call_values",
    "insert_call",
    "insert_call_from_task",
    "insert_call_from_task_with_connection",
]