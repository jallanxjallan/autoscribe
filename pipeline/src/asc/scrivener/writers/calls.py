from __future__ import annotations

"""Ledger writer for call records.

DEBT: CALLS_TABLE belongs in asc.scrivener.contracts or asc.scrivener.schema
once table/action/model mappings are centralized next week.
"""

from typing import Any

from asc.scrivener.connect import LedgerConnection, connect
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.writers.common import insert_row, load_source_key, model_json, redis_key


CALLS_TABLE = "calls"


def insert_call_from_task(task: object) -> None:
    with connect() as conn:
        insert_call_from_task_with_connection(conn=conn, task=task)


def insert_call_from_task_with_connection(*, conn: LedgerConnection, task: object) -> None:
    ensure_ledger_schema(conn)
    insert_call(conn=conn, task=task)


def insert_call(*, conn: LedgerConnection, task: object) -> None:
    record = load_source_key(task.source_key)
    insert_row(conn, CALLS_TABLE, call_values(task, record))


def call_values(task: object, record: object | None = None) -> dict[str, Any]:
    if record is None:
        record = load_source_key(task.source_key)

    key = redis_key(task.source_key)
    return {
        "identity": key.identity,
        "source_identity": key.identity,
        "source_json": model_json(record),
        "created_at": int(record.created_at),
    }


__all__ = [
    "CALLS_TABLE",
    "call_values",
    "insert_call",
    "insert_call_from_task",
    "insert_call_from_task_with_connection",
]
