from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from asc.ledger.connect import LedgerConnection, connect
from asc.ledger.queries import (
    INSERT_RESULT_SQL,
    RESULT_COLUMNS,
    SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL,
    SELECT_RESULT_BY_CALL_SQL,
    SELECT_RESULT_SQL,
    SELECT_RESULTS_SQL,
)
from asc.ledger.schema import ensure_ledger_views
from asc.ledger.step_record import result_timestamp
from asc.ledger.util import fetch_all_dicts, fetch_one_dict, model_value
from asc.ledger.views import (
    SELECT_DUPLICATE_PENDING_EXPORT_ROWS_SQL,
    SELECT_DUPLICATE_PENDING_EXPORT_SLUGS_SQL,
    SELECT_PENDING_RESULT_EXPORTS_SQL,
)
from asc.models.runtime.result import StepResultRecord


def insert_result_record(
    result: StepResultRecord,
    *,
    terminal_step_id: int,
) -> None:
    """Open the configured ledger and write one terminal result pointer."""

    with connect() as conn:
        insert_result_record_with_connection(
            conn=conn,
            result=result,
            terminal_step_id=terminal_step_id,
        )


def insert_result_records(
    results: Sequence[tuple[StepResultRecord, int]],
) -> None:
    """Open the configured ledger and write terminal result pointers."""

    with connect() as conn:
        insert_result_records_with_connection(conn=conn, results=results)


def insert_result_record_with_connection(
    *,
    conn: LedgerConnection,
    result: StepResultRecord,
    terminal_step_id: int,
    commit: bool = True,
) -> None:
    """Write one minimal result pointer for a successful terminal step."""

    conn.execute(INSERT_RESULT_SQL, result_values(result, terminal_step_id=terminal_step_id))
    if commit:
        conn.commit()


def insert_result_records_with_connection(
    *,
    conn: LedgerConnection,
    results: Sequence[tuple[StepResultRecord, int]],
) -> None:
    """Write terminal result pointers using an existing ledger connection."""

    for result, terminal_step_id in results:
        conn.execute(INSERT_RESULT_SQL, result_values(result, terminal_step_id=terminal_step_id))
    conn.commit()


def read_result_record(result_identity: str) -> dict[str, Any] | None:
    """Open the configured ledger and read one result pointer by result identity."""

    with connect() as conn:
        return read_result_record_with_connection(
            conn=conn,
            result_identity=result_identity,
        )


def read_result_record_by_call(call_identity: str) -> dict[str, Any] | None:
    """Open the configured ledger and read one result pointer by call identity."""

    with connect() as conn:
        return read_result_record_by_call_with_connection(
            conn=conn,
            call_identity=call_identity,
        )


def read_result_records() -> list[dict[str, Any]]:
    """Open the configured ledger and read all result pointers."""

    with connect() as conn:
        return read_result_records_with_connection(conn=conn)


def read_extract_result_record_by_call_identity(
    call_identity: str,
) -> dict[str, Any] | None:
    """Open the configured ledger and read one export-ready result row."""

    with connect() as conn:
        return read_extract_result_record_by_call_identity_with_connection(
            conn=conn,
            call_identity=call_identity,
        )


def read_pending_result_export_records() -> list[dict[str, Any]]:
    """Open the configured ledger and read joined call/result rows pending export."""

    with connect() as conn:
        return read_pending_result_export_records_with_connection(conn=conn)


def read_duplicate_pending_export_slugs() -> list[dict[str, Any]]:
    """Open the configured ledger and read prompt slugs with multiple pending exports."""

    with connect() as conn:
        return read_duplicate_pending_export_slugs_with_connection(conn=conn)


def read_duplicate_pending_export_rows() -> list[dict[str, Any]]:
    """Open the configured ledger and read pending export rows for duplicated prompt slugs."""

    with connect() as conn:
        return read_duplicate_pending_export_rows_with_connection(conn=conn)


def require_unique_pending_export_slugs() -> None:
    """Raise if any prompt slug has more than one pending export row."""

    with connect() as conn:
        require_unique_pending_export_slugs_with_connection(conn=conn)


def read_result_record_with_connection(
    *,
    conn: LedgerConnection,
    result_identity: str,
) -> dict[str, Any] | None:
    return fetch_one_dict(conn, SELECT_RESULT_SQL, (result_identity,))


def read_result_record_by_call_with_connection(
    *,
    conn: LedgerConnection,
    call_identity: str,
) -> dict[str, Any] | None:
    return fetch_one_dict(conn, SELECT_RESULT_BY_CALL_SQL, (call_identity,))


def read_result_records_with_connection(
    *,
    conn: LedgerConnection,
) -> list[dict[str, Any]]:
    return fetch_all_dicts(conn, SELECT_RESULTS_SQL)


def read_extract_result_record_by_call_identity_with_connection(
    *,
    conn: LedgerConnection,
    call_identity: str,
) -> dict[str, Any] | None:
    rows = fetch_all_dicts(conn, SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL, (call_identity,))

    if len(rows) > 1:
        raise ValueError(f"more than one result row for call {call_identity}")

    if not rows:
        return None

    return rows[0]


def read_pending_result_export_records_with_connection(
    *,
    conn: LedgerConnection,
) -> list[dict[str, Any]]:
    ensure_ledger_views(conn)
    return fetch_all_dicts(conn, SELECT_PENDING_RESULT_EXPORTS_SQL)


def read_duplicate_pending_export_slugs_with_connection(
    *,
    conn: LedgerConnection,
) -> list[dict[str, Any]]:
    ensure_ledger_views(conn)
    return fetch_all_dicts(conn, SELECT_DUPLICATE_PENDING_EXPORT_SLUGS_SQL)


def read_duplicate_pending_export_rows_with_connection(
    *,
    conn: LedgerConnection,
) -> list[dict[str, Any]]:
    ensure_ledger_views(conn)
    return fetch_all_dicts(conn, SELECT_DUPLICATE_PENDING_EXPORT_ROWS_SQL)


def require_unique_pending_export_slugs_with_connection(
    *,
    conn: LedgerConnection,
) -> None:
    duplicate_rows = read_duplicate_pending_export_rows_with_connection(conn=conn)
    if not duplicate_rows:
        return

    details = "; ".join(
        f"{row['prompt_slug']} call={row['call_identity']} result={row['result_identity']}"
        for row in duplicate_rows
    )
    raise ValueError(f"duplicate pending export prompt slugs: {details}")


def result_values(result: StepResultRecord, *, terminal_step_id: int) -> tuple[Any, ...]:
    if model_value(result, "content", "response") is None:
        raise ValueError("terminal result pointer requires a successful step response")

    return (
        model_value(result, "identity", "result_identity"),
        model_value(result, "call_identity", "call"),
        terminal_step_id,
        result_timestamp(result),
    )


__all__ = [
    "RESULT_COLUMNS",
    "insert_result_record",
    "insert_result_record_with_connection",
    "insert_result_records",
    "insert_result_records_with_connection",
    "read_extract_result_record_by_call_identity",
    "read_extract_result_record_by_call_identity_with_connection",
    "read_duplicate_pending_export_rows",
    "read_duplicate_pending_export_rows_with_connection",
    "read_duplicate_pending_export_slugs",
    "read_duplicate_pending_export_slugs_with_connection",
    "read_pending_result_export_records",
    "read_pending_result_export_records_with_connection",
    "read_result_record",
    "read_result_record_by_call",
    "read_result_record_by_call_with_connection",
    "read_result_record_with_connection",
    "read_result_records",
    "read_result_records_with_connection",
    "require_unique_pending_export_slugs",
    "require_unique_pending_export_slugs_with_connection",
    "result_values",
]
