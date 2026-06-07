from __future__ import annotations

from typing import Any

from asc.core.timestamp import timestamp
from asc.ledger.connect import LedgerConnection, connect
from asc.ledger.queries import (
    EXPORT_COLUMNS,
    INSERT_EXPORT_SQL,
    SELECT_EXPORT_BY_RESULT_IDENTITY_SQL,
)
from asc.ledger.util import execute_and_commit, fetch_one_dict


def insert_export_record(
    *,
    result_identity: str,
    export_message: str,
    created_at: int | None = None,
) -> None:
    """Open the configured ledger and write one export custody row."""

    with connect() as conn:
        insert_export_record_with_connection(
            conn=conn,
            result_identity=result_identity,
            export_message=export_message,
            created_at=created_at,
        )


def insert_export_record_with_connection(
    *,
    conn: LedgerConnection,
    result_identity: str,
    export_message: str,
    created_at: int | None = None,
) -> None:
    """Write one export custody row using an existing ledger connection."""

    execute_and_commit(
        conn,
        INSERT_EXPORT_SQL,
        export_values(
            result_identity=result_identity,
            export_message=export_message,
            created_at=created_at,
        ),
    )


def read_export_record(
    *,
    result_identity: str,
) -> dict[str, Any] | None:
    """Open the configured ledger and read one export row by result identity."""

    with connect() as conn:
        return read_export_record_with_connection(
            conn=conn,
            result_identity=result_identity,
        )


def read_export_record_with_connection(
    *,
    conn: LedgerConnection,
    result_identity: str,
) -> dict[str, Any] | None:
    """Read one export row by result identity using an existing connection."""

    return fetch_one_dict(
        conn,
        SELECT_EXPORT_BY_RESULT_IDENTITY_SQL,
        (result_identity,),
    )


def export_values(
    *,
    result_identity: str,
    export_message: str,
    created_at: int | None = None,
) -> tuple[Any, ...]:
    exported_at = timestamp() if created_at is None else int(created_at)

    return (
        result_identity,
        export_message,
        exported_at,
    )


__all__ = [
    "EXPORT_COLUMNS",
    "export_values",
    "insert_export_record",
    "insert_export_record_with_connection",
    "read_export_record",
    "read_export_record_with_connection",
]
