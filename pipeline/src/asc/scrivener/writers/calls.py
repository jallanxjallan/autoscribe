"""Ledger writer for call records.

DEBT: CALLS_TABLE belongs in asc.scrivener.contracts or asc.ledger.schema
once table/action/model mappings are centralized.
"""

from typing import Any

from asc.ledger.connect import LedgerConnection, connect
from asc.ledger.schema import ensure_ledger_schema
from asc.scrivener.writers.common import (
    insert_row,
    load_task_record,
    model_json,
    optional_domain_identity,
    task_call_identity,
)


CALLS_TABLE = "calls"


def insert_call_from_task(task: object) -> None:
    with connect() as conn:
        insert_call_from_task_with_connection(conn=conn, task=task)


def insert_call_from_task_with_connection(*, conn: LedgerConnection, task: object) -> None:
    ensure_ledger_schema(conn)
    insert_call(conn=conn, task=task)


def insert_call(*, conn: LedgerConnection, task: object) -> None:
    record = load_task_record(task)
    insert_row(conn, CALLS_TABLE, call_values(task, record))


def call_values(task: Any, record: object | None = None) -> dict[str, Any]:
    if record is None:
        record = load_task_record(task)

    call_identity = task_call_identity(task)
    source_identity = optional_domain_identity(
        record,
        "source_identity",
        "record_identity",
        "document_identity",
    ) or call_identity

    return {
        "identity": call_identity,
        "source_identity": source_identity,
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
