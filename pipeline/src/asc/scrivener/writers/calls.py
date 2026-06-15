from __future__ import annotations

from typing import Any

from asc.scrivener.connect import LedgerConnection, connect
from asc.scrivener.queries import INSERT_CALL_SQL
from asc.scrivener.schema import ensure_ledger_schema
from asc.scrivener.util import execute_and_commit, model_json_blob, model_value, timestamp_now


def insert_call_from_job(job: object) -> None:
    with connect() as conn:
        insert_call_from_job_with_connection(conn=conn, job=job)


def insert_call_from_job_with_connection(*, conn: LedgerConnection, job: object) -> None:
    ensure_ledger_schema(conn)
    insert_call_values(conn=conn, values=call_values(job))


def insert_call_values(*, conn: LedgerConnection, values: tuple[Any, ...]) -> None:
    execute_and_commit(conn, INSERT_CALL_SQL, values)


def call_values(job: object) -> tuple[Any, ...]:
    call_identity = model_value(job, "call", "call_identity", "identity")
    plan = model_value(job, "plan", "plan_slug")
    record_identity = model_value(job, "record_identity", "prompt_slug", "slug")
    created_at = model_value(job, "created_at", default=timestamp_now())

    missing = [
        name
        for name, value in (
            ("call/call_identity/identity", call_identity),
            ("plan/plan_slug", plan),
            ("record_identity/prompt_slug/slug", record_identity),
        )
        if value is None
    ]
    if missing:
        raise ValueError(f"scrivener job missing required call ledger fields: {', '.join(missing)}")

    return (
        str(call_identity),
        str(plan),
        str(record_identity),
        model_json_blob(job),
        int(created_at),
    )


__all__ = [
    "call_values",
    "insert_call_from_job",
    "insert_call_from_job_with_connection",
    "insert_call_values",
]
