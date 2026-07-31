"""Read pending export rows from the reduced ledger."""

from __future__ import annotations

from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.queries import (
    SELECT_PENDING_EXPORT_BY_SOURCE_IDENTITY_SQL,
    SELECT_PENDING_EXPORTS_SQL,
)


def pending_export_records(
    *,
    conn: LedgerConnection,
    source_identity: str | None = None,
) -> list[dict[str, Any]]:
    """Return pending export rows with legacy-friendly aliases.

    In the reduced ledger, a pending export is a successful terminal result
    with no delivery receipt in ``exports``.
    """

    if source_identity is None:
        rows = conn.execute(SELECT_PENDING_EXPORTS_SQL).fetchall()
    else:
        rows = conn.execute(
            SELECT_PENDING_EXPORT_BY_SOURCE_IDENTITY_SQL,
            (source_identity,),
        ).fetchall()
    return [_normalize_pending_row(row) for row in rows]


def _normalize_pending_row(row: Any) -> dict[str, Any]:
    data = {key: row[key] for key in row.keys()}
    record_identity = data.get("record_identity")
    call_identity = data.get("call_identity")

    # Existing CLI/writeback code has used several names for the same values.
    data.setdefault("slug", record_identity)
    data.setdefault("source_identity", record_identity)
    data.setdefault("result_identity", call_identity)
    data.setdefault("identity", call_identity)
    data.setdefault("exported_at", None)
    data.setdefault("exported_at_text", "")
    return data


__all__ = ["pending_export_records"]
