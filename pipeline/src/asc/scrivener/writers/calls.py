from __future__ import annotations

from typing import Any

from asc.scrivener.connect import LedgerConnection, connect
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.write import call_values, insert_call


def insert_call_from_job(job: object) -> None:
    with connect() as conn:
        insert_call_from_job_with_connection(conn=conn, job=job)


def insert_call_from_job_with_connection(*, conn: LedgerConnection, job: object) -> None:
    ensure_ledger_schema(conn)
    insert_call(conn=conn, job=job)


def insert_call_values(*, conn: LedgerConnection, values: tuple[Any, ...]) -> None:
    from asc.scrivener.queries import INSERT_CALL_SQL
    from asc.scrivener.util import execute_and_commit

    execute_and_commit(conn, INSERT_CALL_SQL, values)


__all__ = [
    "call_values",
    "insert_call_from_job",
    "insert_call_from_job_with_connection",
    "insert_call_values",
]
