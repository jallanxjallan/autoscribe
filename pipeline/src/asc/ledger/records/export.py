"""Export custody writes owned by asc.ledger."""

from typing import Any

from asc.ledger.connect import LedgerConnection
from asc.ledger.maps import EXPORTS_TABLE
from asc.ledger.sql import insert_row
from asc.ledger.util import json_blob, optional_text, timestamp_now


def insert_export_record_with_connection(
    *,
    conn: LedgerConnection,
    result_identity: str,
    export_message: str,
    destination: str | None = None,
    export_mode: str = "manual",
    target_slug: str | None = None,
    target_path: str | None = None,
    consumer_data: dict[str, Any] | None = None,
) -> None:
    """Record an export/writeback receipt for a terminal result.

    ``result_identity`` may be a call identity or a full result key such as
    ``result:<identity>:<step>``. The result table is keyed by call identity.
    """

    now = int(timestamp_now())
    row = {
        "result_identity": _identity_part(result_identity),
        "destination": optional_text(destination),
        "export_mode": optional_text(export_mode) or "manual",
        "target_slug": optional_text(target_slug),
        "target_path": optional_text(target_path),
        "exported_at": now,
        "export_message": optional_text(export_message),
        "consumer_json": None if consumer_data is None else json_blob(consumer_data),
        "created_at": now,
    }
    insert_row(conn, table=EXPORTS_TABLE, data=row)


def _identity_part(value: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("result_identity must be non-empty")
    parts = text.split(":")
    if len(parts) >= 2:
        return parts[1]
    return text


__all__ = ["insert_export_record_with_connection"]
