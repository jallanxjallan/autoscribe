from __future__ import annotations

from typing import Any

from asc.scrivener.connect import LedgerConnection, connect
from asc.scrivener.queries import INSERT_CALL_SQL
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.util import execute_and_commit, timestamp_now
from asc.scrivener.writers.common import (
    ledger_identity,
    load_job_input,
    optional,
    record_blob,
    source_identity,
)


def insert_call_from_job(job: object) -> None:
    with connect() as conn:
        insert_call_from_job_with_connection(conn=conn, job=job)


def insert_call_from_job_with_connection(*, conn: LedgerConnection, job: object) -> None:
    ensure_ledger_schema(conn)
    insert_call(conn=conn, job=job)


def insert_call(*, conn: LedgerConnection, job: object) -> None:
    execute_and_commit(conn, INSERT_CALL_SQL, call_values(job))


def call_values(job: object) -> tuple[Any, ...]:
    record = load_job_input(job)
    return (
        ledger_identity(job),
        source_identity(job, record),
        record_blob(record, fallback=job),
        int(optional(record, "created_at", default=optional(job, "created_at", default=timestamp_now()))),
    )


__all__ = [
    "call_values",
    "insert_call",
    "insert_call_from_job",
    "insert_call_from_job_with_connection",
]
