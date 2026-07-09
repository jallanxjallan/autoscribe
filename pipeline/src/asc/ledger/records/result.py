"""Response/export query APIs owned by asc.ledger."""

from collections import Counter
from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.queries import (
    SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL,
    SELECT_PENDING_EXPORTS_SQL,
)


def read_pending_result_export_records_with_connection(
    *,
    conn: LedgerConnection,
) -> list[dict[str, Any]]:
    rows = conn.execute(SELECT_PENDING_EXPORTS_SQL).fetchall()
    return [_pending_row(row) for row in rows]


def require_unique_pending_export_slugs_with_connection(
    *,
    conn: LedgerConnection,
) -> None:
    rows = read_pending_result_export_records_with_connection(conn=conn)
    counts = Counter(str(row["record_identity"]) for row in rows)
    duplicates = sorted(source for source, count in counts.items() if count > 1)
    if duplicates:
        joined = ", ".join(duplicates)
        raise ValueError(f"multiple pending exports for record_identity: {joined}")


def read_extract_result_record_by_call_identity_with_connection(
    *,
    conn: LedgerConnection,
    call_identity: str,
) -> dict[str, Any] | None:
    row = conn.execute(SELECT_EXTRACT_RESULT_BY_CALL_IDENTITY_SQL, (call_identity,)).fetchone()
    if row is None:
        return None
    data = _row_dict(row)
    data.setdefault("call_identity", data.get("identity"))
    data.setdefault("record_identity", data.get("source_identity"))
    data.setdefault("record_content", data.get("content"))
    data.setdefault("result_identity", data.get("identity"))
    return data


def _pending_row(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    data.setdefault("identity", data.get("call_identity"))
    data.setdefault("source_identity", data.get("record_identity"))
    data.setdefault("result_identity", data.get("call_identity"))
    return data


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


__all__ = [
    "read_extract_result_record_by_call_identity_with_connection",
    "read_pending_result_export_records_with_connection",
    "require_unique_pending_export_slugs_with_connection",
]
