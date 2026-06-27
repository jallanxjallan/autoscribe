"""Export custody writes owned by asc.ledger."""

from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.util import execute_and_commit, timestamp_now


_FIND_EXPORT_IDENTITY_SQL = """
    SELECT identity
    FROM exports
    WHERE identity = ?
       OR result_key = ?
       OR result_key LIKE ?
    ORDER BY created_at ASC, identity ASC
    LIMIT 1
"""

_CONFIRM_EXPORT_BY_IDENTITY_SQL = """
    UPDATE exports
    SET
        exported_at = ?,
        export_message = ?
    WHERE identity = ?
"""


def insert_export_record_with_connection(
    *,
    conn: LedgerConnection,
    result_identity: str,
    export_message: str,
) -> None:
    """Mark one pending export as written back.

    ``result_identity`` may be a call identity, a result identity, or a full
    result key such as ``transform:<identity>:<step>``.
    """

    identity = _resolve_export_identity(conn=conn, result_identity=result_identity)
    execute_and_commit(
        conn,
        _CONFIRM_EXPORT_BY_IDENTITY_SQL,
        (int(timestamp_now()), export_message, identity),
    )


def _resolve_export_identity(*, conn: LedgerConnection, result_identity: str) -> str:
    text = str(result_identity).strip()
    if not text:
        raise ValueError("result_identity must be non-empty")

    identity = _identity_part(text)
    like = f"%:{identity}:%"
    row = conn.execute(_FIND_EXPORT_IDENTITY_SQL, (text, text, like)).fetchone()
    if row is None:
        raise ValueError(f"no export row found for result_identity: {text}")
    return str(row["identity"])


def _identity_part(value: str) -> str:
    parts = value.split(":")
    if len(parts) >= 2:
        return parts[1]
    return value


__all__ = ["insert_export_record_with_connection"]
