"""Result/export query APIs owned by asc.ledger.

These functions preserve the older ``asc.scrivener.records.result`` contract
while moving the SQL read boundary into ``asc.ledger``.
"""

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
    counts = Counter(str(row["source_identity"]) for row in rows)
    duplicates = sorted(source for source, count in counts.items() if count > 1)
    if duplicates:
        joined = ", ".join(duplicates)
        raise ValueError(f"multiple pending exports for source_identity: {joined}")


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
    data.setdefault("result_identity", _result_identity(data.get("result_key")))
    return data


def _pending_row(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    data["call_identity"] = data.get("identity")
    data["record_identity"] = data.get("source_identity")
    data["result_identity"] = _result_identity(data.get("result_key"))
    return data


def _result_identity(result_key: object) -> str:
    text = str(result_key or "").strip()
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) >= 2:
        return parts[1]
    return text


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


__all__ = [
    "read_extract_result_record_by_call_identity_with_connection",
    "read_pending_result_export_records_with_connection",
    "require_unique_pending_export_slugs_with_connection",
]
