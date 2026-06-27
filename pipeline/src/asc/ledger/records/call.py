"""Call-record queries owned by asc.ledger."""

from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.queries import SELECT_CALL_SQL


def read_call_record_with_connection(
    *,
    conn: LedgerConnection,
    call_identity: str,
) -> dict[str, Any] | None:
    row = conn.execute(SELECT_CALL_SQL, (call_identity,)).fetchone()
    return _row_dict(row) if row is not None else None


def _row_dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


__all__ = ["read_call_record_with_connection"]
