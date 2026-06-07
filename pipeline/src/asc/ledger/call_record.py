from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from asc.ledger.connect import LedgerConnection, connect
from asc.ledger.queries import (
    CALL_COLUMNS,
    INSERT_CALL_SQL,
    SELECT_CALL_IDENTITIES_FOR_PLAN_SQL,
    SELECT_CALL_SQL,
    SELECT_CALLS_FOR_PLAN_SQL,
    SELECT_CALLS_SQL,
)
from asc.ledger.util import (
    execute_and_commit,
    executemany_and_commit,
    fetch_all_dicts,
    fetch_first_column,
    fetch_one_dict,
    model_json_blob,
    model_value,
)
from asc.models.runtime.call import CallRecord


def insert_call_record(call: CallRecord) -> None:
    with connect() as conn:
        insert_call_record_with_connection(conn=conn, call=call)


def insert_call_records(calls: Sequence[CallRecord]) -> None:
    with connect() as conn:
        insert_call_records_with_connection(conn=conn, calls=calls)


def insert_call_record_with_connection(
    *,
    conn: LedgerConnection,
    call: CallRecord,
) -> None:
    execute_and_commit(conn, INSERT_CALL_SQL, call_values(call))


def insert_call_records_with_connection(
    *,
    conn: LedgerConnection,
    calls: Sequence[CallRecord],
) -> None:
    executemany_and_commit(conn, INSERT_CALL_SQL, [call_values(call) for call in calls])


def read_call_record(call_identity: str) -> dict[str, Any] | None:
    with connect() as conn:
        return read_call_record_with_connection(conn=conn, call_identity=call_identity)


def read_call_records_for_plan(plan: str) -> list[dict[str, Any]]:
    with connect() as conn:
        return read_call_records_for_plan_with_connection(conn=conn, plan=plan)


def read_call_identities_for_plan(plan: str) -> list[str]:
    with connect() as conn:
        return read_call_identities_for_plan_with_connection(conn=conn, plan=plan)


def read_call_records() -> list[dict[str, Any]]:
    with connect() as conn:
        return read_call_records_with_connection(conn=conn)


def read_call_record_with_connection(
    *,
    conn: LedgerConnection,
    call_identity: str,
) -> dict[str, Any] | None:
    return fetch_one_dict(conn, SELECT_CALL_SQL, (call_identity,))


def read_call_records_for_plan_with_connection(
    *,
    conn: LedgerConnection,
    plan: str,
) -> list[dict[str, Any]]:
    return fetch_all_dicts(conn, SELECT_CALLS_FOR_PLAN_SQL, (plan,))


def read_call_identities_for_plan_with_connection(
    *,
    conn: LedgerConnection,
    plan: str,
) -> list[str]:
    return fetch_first_column(conn, SELECT_CALL_IDENTITIES_FOR_PLAN_SQL, (plan,))


def read_call_records_with_connection(
    *,
    conn: LedgerConnection,
) -> list[dict[str, Any]]:
    return fetch_all_dicts(conn, SELECT_CALLS_SQL)


def call_values(call: CallRecord) -> tuple[Any, ...]:
    return (
        model_value(call, "identity", "call_identity", "call"),
        model_value(call, "plan"),
        model_json_blob(model_value(call, "raw_json", "raw_record")),
        model_value(call, "created_at"),
    )


# Transitional aliases for older callers. Prefer plan/call names in new code.
read_call_records_for_job = read_call_records_for_plan
read_call_records_for_job_with_connection = read_call_records_for_plan_with_connection
read_call_identities_for_job = read_call_identities_for_plan
read_call_identities_for_job_with_connection = read_call_identities_for_plan_with_connection


__all__ = [
    "CALL_COLUMNS",
    "call_values",
    "insert_call_record",
    "insert_call_record_with_connection",
    "insert_call_records",
    "insert_call_records_with_connection",
    "read_call_identities_for_plan",
    "read_call_identities_for_plan_with_connection",
    "read_call_record",
    "read_call_record_with_connection",
    "read_call_records",
    "read_call_records_for_plan",
    "read_call_records_for_plan_with_connection",
    "read_call_records_with_connection",
    "read_call_identities_for_job",
    "read_call_identities_for_job_with_connection",
    "read_call_records_for_job",
    "read_call_records_for_job_with_connection",
]
